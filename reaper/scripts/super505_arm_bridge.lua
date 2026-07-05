-- super505_arm_bridge.lua — mirror looper-channel record state onto source tracks
--
-- The Super505 JSFX publishes (gmem namespace "Super505"):
--   gmem[0] = heartbeat (increments every audio block while the FX runs)
--   gmem[1] = want-input bitmask (bit N = looper channel N+1 is armed for a
--             quantized record start, recording/overdubbing, or counting in)
--   gmem[2] = looper channel count
--
-- TWO-WAY mirror: whenever the mask changes, every REAPER track that sends into
-- the looper is reconciled --
--   * feeds a channel that wants input  -> record-armed (+ input monitoring on)
--   * feeds only idle/playing channels  -> DISARMED
-- so a source track is armed exactly while its looper row records. The mapping
-- follows the receives on the looper track (project routing, not track order).
--
-- Note the trade-off: while a row is idle/playing, its source track is unarmed,
-- so that instrument's LIVE input no longer reaches the looper's monitor path.
--
-- Tracks that do NOT send into the looper are never touched. Reconciliation
-- runs only when the mask CHANGES, so manual arm tweaks between looper events
-- stick until the next rec press / record close.
--
-- Install: run once per session (Actions -> Load ReaScript), or let
-- Scripts/__startup.lua launch it automatically at REAPER startup.

local NS = "Super505"

reaper.gmem_attach(NS)

local last_mask = 0
local last_hb = -1
local hb_idle = 0
local looper = nil
local warned = 0 -- bits already warned about (no source found), cleared on bit fall

local function find_looper_track()
  for i = 0, reaper.CountTracks(0) - 1 do
    local tr = reaper.GetTrack(0, i)
    for fx = 0, reaper.TrackFX_GetCount(tr) - 1 do
      local ok, name = reaper.TrackFX_GetFXName(tr, fx, "")
      if ok and name:lower():find("super505") and not name:lower():find("mixdown") then
        return tr
      end
    end
  end
  return nil
end

-- Reconcile every looper-feeding track's arm state against the want mask.
-- `rising` = bits that just turned on (used for missing-send warnings only).
local function reconcile(mask, rising)
  if not (looper and reaper.ValidatePtr2(0, looper, "MediaTrack*")) then
    looper = find_looper_track()
    if not looper then return end
  end

  local bytrack = {}   -- guid -> {tr=MediaTrack, wanted=bool}
  local covered = 0    -- channels that have at least one feeding send
  for i = 0, reaper.GetTrackNumSends(looper, -1) - 1 do
    local dst = math.floor(reaper.GetTrackSendInfo_Value(looper, -1, i, "I_DSTCHAN"))
    local chans = (dst >= 1024) and { dst - 1024 } or { dst, dst + 1 }
    local src = reaper.GetTrackSendInfo_Value(looper, -1, i, "P_SRCTRACK")
    if src and reaper.ValidatePtr2(0, src, "MediaTrack*") then
      local guid = reaper.GetTrackGUID(src)
      local e = bytrack[guid]
      if not e then
        e = { tr = src, wanted = false }
        bytrack[guid] = e
      end
      for _, ch in ipairs(chans) do
        covered = covered | (1 << ch)
        if (mask & (1 << ch)) ~= 0 then e.wanted = true end
      end
    end
  end

  for _, e in pairs(bytrack) do
    local want = e.wanted and 1 or 0
    if reaper.GetMediaTrackInfo_Value(e.tr, "I_RECARM") ~= want then
      reaper.SetMediaTrackInfo_Value(e.tr, "I_RECARM", want)
    end
    if e.wanted and reaper.GetMediaTrackInfo_Value(e.tr, "I_RECMON") == 0 then
      reaper.SetMediaTrackInfo_Value(e.tr, "I_RECMON", 1)
    end
  end

  -- warn (once per episode) about wanted channels that nothing feeds
  local orphan = rising & ~covered & ~warned
  for ch = 0, 15 do
    if (orphan & (1 << ch)) ~= 0 then
      warned = warned | (1 << ch)
      reaper.ShowConsoleMsg(("super505_arm_bridge: no track sends into looper channel %d - add a send (Track -> Super505 Looper, dest channel %d)\n")
        :format(ch + 1, ch + 1))
    end
  end
end

local function tick()
  local hb = reaper.gmem_read(0)
  if hb ~= last_hb then
    last_hb = hb
    hb_idle = 0
  else
    hb_idle = hb_idle + 1
  end

  -- only react while the looper FX is actually running (heartbeat advancing)
  if hb_idle < 60 then
    local mask = math.floor(reaper.gmem_read(1) or 0)
    if mask ~= last_mask then
      local rising = mask & ~last_mask
      warned = warned & mask            -- forget warnings for cleared bits
      reconcile(mask, rising)
      last_mask = mask
    end
  end

  reaper.defer(tick)
end

tick()
