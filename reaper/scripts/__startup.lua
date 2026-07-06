-- REAPER runs Scripts/__startup.lua automatically at launch.
-- Start the RiftwayLabsLooper arm bridge (record-arms source tracks when looper
-- channels arm/record). Harmless when no RiftwayLabsLooper project is open: the
-- bridge idles until the JSFX heartbeat appears.
dofile(reaper.GetResourcePath() .. "/Scripts/RiftwayLabsLooper_arm_bridge.lua")
