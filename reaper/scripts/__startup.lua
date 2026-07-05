-- REAPER runs Scripts/__startup.lua automatically at launch.
-- Start the Super505 arm bridge (record-arms source tracks when looper
-- channels arm/record). Harmless when no Super505 project is open: the
-- bridge idles until the JSFX heartbeat appears.
dofile(reaper.GetResourcePath() .. "/Scripts/super505_arm_bridge.lua")
