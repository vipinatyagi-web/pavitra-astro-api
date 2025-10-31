from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import swisseph as swe
import datetime, os

app = FastAPI(title="Pavitra Gyaan Astro API")

EPH_PATH = os.getenv("EPH_PATH", "")
if EPH_PATH and os.path.exists(EPH_PATH):
    swe.set_ephe_path(EPH_PATH)

def local_to_jd_utc(dob: str, tob: str, tz_offset_minutes: int):
    try:
        dt = datetime.datetime.strptime(dob + " " + tob, "%Y-%m-%d %H:%M")
    except Exception:
        raise ValueError("Invalid dob/tob format (YYYY-MM-DD and HH:MM 24h)")
    dt_utc = dt - datetime.timedelta(minutes=tz_offset_minutes)
    year, month, day = dt_utc.year, dt_utc.month, dt_utc.day
    hour = dt_utc.hour + dt_utc.minute/60.0 + dt_utc.second/3600.0
    jd = swe.julday(year, month, day, hour)
    return jd

def lon_to_sign_deg(lon):
    lon = lon % 360.0
    sign_index = int(lon // 30)
    signs = ['Aries','Taurus','Gemini','Cancer','Leo','Virgo','Libra','Scorpio','Sagittarius','Capricorn','Aquarius','Pisces']
    degree = lon % 30
    return signs[sign_index], round(degree,2)

def whole_sign_house_from_asc(asc_lon, planet_lon):
    asc_sign = int((asc_lon % 360) // 30)
    p_sign = int((planet_lon % 360) // 30)
    house = ((p_sign - asc_sign) % 12) + 1
    return house

class ChartIn(BaseModel):
    full_name: str | None = None
    dob: str
    tob: str
    lat: float
    lon: float
    tz_offset_minutes: int
    ayanamsa: str | None = "Lahiri"
    house_system: str | None = "WholeSign"

@app.post("/compute")
def compute(chart: ChartIn):
    try:
        jd_ut = local_to_jd_utc(chart.dob, chart.tob, chart.tz_offset_minutes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    planet_ids = {
        'sun': swe.SUN, 'moon': swe.MOON, 'mars': swe.MARS,
        'mercury': swe.MERCURY, 'jupiter': swe.JUPITER,
        'venus': swe.VENUS, 'saturn': swe.SATURN, 'rahu': swe.MEAN_NODE
    }

    planets = {}
    for name, pid in planet_ids.items():
        res = swe.calc_ut(jd_ut, pid)
        lon = res[0] % 360.0
        speed = res[3] if len(res) > 3 else 0.0
        sign, deg = lon_to_sign_deg(lon)
        planets[name] = {"lon": round(lon,6), "sign": sign, "deg": deg, "retro": speed < 0}

    try:
        cusps, ascmc = swe.houses(jd_ut, chart.lat, chart.lon)
        asc = ascmc[0]
    except Exception:
        asc = planets['sun']['lon']

    houses = {}
    if (chart.house_system or "WholeSign").lower().startswith("whole"):
        for pname, pinfo in planets.items():
            houses[pname] = whole_sign_house_from_asc(asc, pinfo["lon"])
    else:
        for pname in planets.keys():
            houses[pname] = None

    rule_hits = []
    if houses.get("sun") == 10:
        rule_hits.append({"code":"CAREER_SUN_10","reason":"Sun in 10th house — leadership focus"})
    if houses.get("mars") == 7:
        rule_hits.append({"code":"MARR_MARS_7","reason":"Mars in 7th — partnership challenges"})

    return {
        "swisseph_version": getattr(swe, "__version__", "unknown"),
        "jd_ut": round(jd_ut,6),
        "ascendant_lon": round(asc,6),
        "planets": planets,
        "houses_whole_sign": houses,
        "rule_hits": rule_hits,
        "ayanamsa": chart.ayanamsa,
        "house_system": chart.house_system
    }
