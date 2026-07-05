-- super505_arm_bridge.lua — record-arm source tracks when looper channels want input
--
-- The Super505 JSFX publishes (gmem namespace "Super505"):
--   gmem[0] = heartbeat (increments every audio block while the FX runs)
--   gmem[1] = want-input bitmask (bit N = looper channel N+1 is armed for a
--             quantized record start, recording/overdubbing, or counting in)
--   gmem[2] = looper channel count
--
-- When a bit RISES, this script finds every REAPER track that sends into that
-- looper channel (so the mapping follows the project routing, not track order)
-- and record-arms it + enables input monitoring. REAPER only passes live input
-- through armed, monitored tracks, so without this the looper records silence.
--
-- One-way by design: the bridge never DISARMS tracks (disarming would cut live
-- monitoring of that instrument through the looper). Disarm manually if wanted.
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

-- all tracks whose receive on the looper covers looper channel `ch` (0-based)
local function sources_for_channel(lp, ch)
  local out = {}
  for i = 0, reaper.GetTrackNumSends(lp, -1) - 1 do
    local dst = math.floor(reaper.GetTrackSendInfo_Value(lp, -1, i, "I_DSTCHAN"))
    local covered
    if dst >= 1024 then                    -- mono receive into channel (dst-1024)
      covered = (dst - 1024) == ch
    else                                   -- stereo receive into dst / dst+1
      covered = dst == ch or (dst + 1) == ch
    end
    if covered then
      local src = reaper.GetTrackSendInfo_Value(lp, -1, i, "P_SRCTRACK")
      if src and reaper.ValidatePtr2(0, src, "MediaTrack*") then
        out[#out + 1] = src
      end
    end
  end
  return out
end

local function arm_sources(ch)
  if not (looper and reaper.ValidatePtr2(0, looper, "MediaTrack*")) then
    looper = find_looper_track()
    if not looper then return false end
  end
  local srcs = sources_for_channel(looper, ch)
  if #srcs == 0 then return false end
  for _, tr in ipairs(srcs) do
    if reaper.GetMediaTrackInfo_Value(tr, "I_RECARM") ~= 1 then
      reaper.SetMediaTrackInfo_Value(tr, "I_RECARM", 1)
    end
    if reaper.GetMediaTrackInfo_Value(tr, "I_RECMON") == 0 then
      reaper.SetMediaTrackInfo_Value(tr, "I_RECMON", 1)
    end
  end
  return true
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
      if rising ~= 0 then
        for ch = 0, 15 do
          local bit = 1 << ch
          if (rising & bit) ~= 0 then
            if not arm_sources(ch) and (warned & bit) == 0 then
              warned = warned | bit
              reaper.ShowConsoleMsg(("super505_arm_bridge: no track sends into looper channel %d - add a send (Track -> Super505 Looper, dest channel %d)\n")
                :format(ch + 1, ch + 1))
            end
          end
        end
      end
      last_mask = mask
    end
  end

  reaper.defer(tick)
end

tick()
