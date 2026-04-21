from app.services.ad_broadcasts import AdBroadcastService

assert AdBroadcastService.schedule_label(AdBroadcastService.build_schedule_code(1,0)) == "1 раз сразу"
assert AdBroadcastService.schedule_label(AdBroadcastService.build_schedule_code(1,3)) == "1 раз через 3 часа"
assert AdBroadcastService.schedule_label(AdBroadcastService.build_schedule_code(2,24)) == "2 раза, интервал — раз в 1 день"
assert AdBroadcastService.schedule_label(AdBroadcastService.build_schedule_code(4,72)) == "4 раза, интервал — раз в 3 дня"
assert AdBroadcastService.list_interval_options(1) == [0,3,6,12,24,48,72]
assert AdBroadcastService.list_interval_options(3) == [3,6,12,24,48,72]
print("OK: broadcast schedule options smoke test passed")
