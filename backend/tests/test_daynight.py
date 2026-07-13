"""DayNightSystem 单元测试。"""

from digimon_world.world.daynight import (
    DayNightSystem,
    DayPeriod,
    reset_daynight_system,
)


def test_daynight_starts_as_day_by_default():
    dn = DayNightSystem()
    assert dn.period == DayPeriod.NIGHT  # 默认午夜
    assert not dn.is_daytime
    assert dn.is_nighttime
    assert dn.icon == "\U0001f319"  # 🌙
    assert dn.label == "黑夜"


def test_daynight_starts_with_custom_minutes():
    # 360 min = 06:00 = day
    dn = DayNightSystem(start_minutes=360)
    assert dn.period == DayPeriod.DAY  # 360 min = 06:00 = 白天

    # 1080 min = 18:00 = night
    dn = DayNightSystem(start_minutes=1080)
    assert dn.period == DayPeriod.NIGHT


def test_daynight_noon_is_day():
    # 720 min = 12:00
    dn = DayNightSystem(start_minutes=720)
    assert dn.is_daytime


def test_daynight_midnight_is_night():
    # 0 min = 00:00
    dn = DayNightSystem(start_minutes=0)
    assert dn.is_nighttime


def test_daynight_update_switches_period():
    dn = DayNightSystem(start_minutes=300)  # 05:00 = night
    assert dn.is_nighttime

    switched = dn.update(360)  # 06:00 = day
    assert switched
    assert dn.is_daytime


def test_daynight_update_same_period_no_switch():
    dn = DayNightSystem(start_minutes=600)  # 10:00 = day
    switched = dn.update(660)  # 11:00 = still day
    assert not switched
    assert dn.is_daytime


def test_daynight_modifiers_night():
    dn = DayNightSystem(start_minutes=1200)  # 20:00 = night
    assert dn.is_nighttime

    # 夜间移动 -30%
    assert dn.modifier("movement") == 0.70
    # 夜间社交 -20%
    assert dn.modifier("social") == 0.80
    # 其他维度中性
    assert dn.modifier("battle") == 1.0
    assert dn.modifier("foraging") == 1.0


def test_daynight_modifiers_day():
    dn = DayNightSystem(start_minutes=600)  # 10:00 = day
    assert dn.is_daytime

    # 白天所有行为中性
    assert dn.modifier("movement") == 1.0
    assert dn.modifier("social") == 1.0
    assert dn.modifier("battle") == 1.0


def test_daynight_species_night_active():
    """巴达兽(tailmon)和迪路兽(patamon)夜间更活跃"""
    dn = DayNightSystem(start_minutes=1200)  # night

    # patamon 夜间移动不减反增
    assert dn.species_modifier("patamon", "movement") == 1.10
    assert dn.species_modifier("tailmon", "movement") == 1.10

    # 其他物种夜间移动正常 -30%
    assert dn.species_modifier("agumon", "movement") == 0.70


def test_daynight_species_fire_daytime():
    """亚古兽(agumon)白天攻击力 +10%"""
    dn = DayNightSystem(start_minutes=600)  # day

    assert dn.species_modifier("agumon", "battle") == 1.10
    assert dn.species_modifier("gabumon", "battle") == 1.0


def test_daynight_to_dict():
    dn = DayNightSystem(start_minutes=720)  # 12:00 = day
    d = dn.to_dict()
    assert d["period"] == "day"
    assert d["is_daytime"]
    assert not d["is_nighttime"]
    assert d["icon"] == "\u2600\ufe0f"
    assert d["time"] == "12:00"
    assert "modifiers" in d
    assert d["modifiers"]["movement"] == 1.0


def test_daynight_time_string():
    dn = DayNightSystem(start_minutes=785)  # 13:05
    assert dn.time_string == "13:05"

    dn = DayNightSystem(start_minutes=1439)  # 23:59
    assert dn.time_string == "23:59"


def test_reset_daynight_system():
    from digimon_world.world.daynight import get_daynight_system

    dn1 = get_daynight_system()
    reset_daynight_system()
    dn2 = get_daynight_system()
    assert dn1 is not dn2
    # 重置后回到默认(0分钟 = 00:00 = 黑夜)
    assert dn2.is_nighttime
