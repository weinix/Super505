-- RiftwayLabsLooper_arm_bridge.lua — record-arm source tracks when looper channels want input
--
-- The RiftwayLabsLooper JSFX publishes (gmem namespace "RiftwayLabs"):
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
-- SELF-HEALING: the looper track is re-discovered (no restart needed) when the
-- heartbeat stalls (FX bypassed/removed/errored) and then resumes, or whenever
-- the cached track no longer holds the looper FX. Healthy-state behavior is
-- unchanged. Light logging marks every (re)discovery / stall / resume.
--
-- Install: run once per session (Actions -> Load ReaScript), or let
-- Scripts/__startup.lua launch it automatically at REAPER startup.

local NS = "RiftwayLabs"
local STALL_TICKS = 60          -- deferred ticks (~2s) w/o heartbeat => FX stopped

reaper.gmem_attach(NS)

local last_mask = 0
local last_hb = -1
local hb_idle = 0
local stalled = false           -- true while the looper FX heartbeat is not advancing
local looper = nil
local warned = 0                -- bits already warned about (no source found)

local function log(msg)
  reaper.ShowConsoleMsg("RiftwayLabsLooper_arm_bridge: " .. msg .. "\n")
end

-- does this track currently hold the (non-mixdown) looper FX?
local function track_has_looper_fx(tr)
  if not (tr and reaper.ValidatePtr2(0, tr, "MediaTrack*")) then return false end
  for fx = 0, reaper.TrackFX_GetCount(tr) - 1 do
    local ok, name = reaper.TrackFX_GetFXName(tr, fx, "")
    if ok and name:lower():find("riftwaylabslooper") and not name:lower():find("mixdown") then
      return true
    end
  end
  return false
end

local function find_looper_track()
  for i = 0, reaper.CountTracks(0) - 1 do
    local tr = reaper.GetTrack(0, i)
    if track_has_looper_fx(tr) then return tr, i end
  end
  return nil
end

-- keep `looper` honest: valid pointer AND still holding the FX; re-discover if not.
-- Returns true when a usable looper track is cached. Logs any change.
local function ensure_looper()
  if looper and track_has_looper_fx(looper) then return true end
  local tr, idx = find_looper_track()
  if tr ~= looper then
    looper = tr
    if looper then
      log(("(re)discovered looper on track %d"):format((idx or 0) + 1))
    else
      log("looper FX not found (missing/disabled?) — will retry")
    end
    last_mask = 0               -- re-evaluate arm state against the fresh track
    warned = 0
  end
  return looper ~= nil
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
  if not ensure_looper() then return false end
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
    if stalled then                        -- FX came back to life
      stalled = false
      log("heartbeat resumed — rediscovering looper")
      looper = nil                         -- force a fresh discovery
      last_mask = 0
      warned = 0
    end
  else
    hb_idle = hb_idle + 1
    if not stalled and hb_idle >= STALL_TICKS then
      stalled = true                       -- FX bypassed / removed / errored
      log("heartbeat stalled — looper FX stopped; pausing until it returns")
    end
  end

  -- only react while the looper FX is actually running (heartbeat advancing)
  if not stalled then
    ensure_looper()                        -- self-heal a stale/re-added FX pointer
    local mask = math.floor(reaper.gmem_read(1) or 0)
    if mask ~= last_mask then
      local rising = mask & ~last_mask
      warned = warned & mask               -- forget warnings for cleared bits
      if rising ~= 0 then
        for ch = 0, 15 do
          local bit = 1 << ch
          if (rising & bit) ~= 0 then
            if not arm_sources(ch) and (warned & bit) == 0 then
              warned = warned | bit
              log(("no track sends into looper channel %d — add a send (Track -> RiftwayLabsLooper, dest channel %d)")
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
