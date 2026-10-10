import numpy as np      # tinh toan so hoc, vector
import pandas           # doc va xu ly du lieu
import folium           # ve ban do
import os               # lam viec voi file va thu muc


BASE_DIR = os.path.dirname(os.path.abspath(__file__))

RTK_FILE = os.path.join(BASE_DIR, "oemv_20090515c.pos")
SINGLE_FILE = os.path.join(BASE_DIR, "oemv_20090515c_single.pos")
OUTPUT_HTML = os.path.join(BASE_DIR, "rtk_vs_single_map.html")

DEG2M = 111320  # đổi độ -> mét (xấp xỉ)


# ĐỌC FILE du lieu ve tinh .POS
def parse_pos(filepath):
    rows = []

    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Không tìm thấy file: {filepath}")

    with open(filepath, "r", errors="ignore") as f:
        for line in f:
            line = line.strip()

            # bỏ header RTKLIB
            if not line or line.startswith("%"):
                continue

            p = line.split()
            if len(p) < 6:
                continue

            try:
                rows.append({
                    "time": f"{p[0]} {p[1]}",
                    "lat": float(p[2]),   # vi do
                    "lon": float(p[3]),
                    "height": float(p[4]),
                    "Q": int(p[5]),       # chat luong nghiem
                })
            except (ValueError, IndexError):
                continue

    df = pandas.DataFrame(rows)

    if not df.empty:
        # parse "time" thành datetime để ghép epoch chính xác ở bước sau
        df["time"] = pandas.to_datetime(df["time"], errors="coerce")
        df = df.dropna(subset=["time"]).reset_index(drop=True)

    return df


# TÍNH SAI SỐ
def compute_stats(rtk, single):
    n = len(rtk)

    fix_n = int((rtk["Q"] == 1).sum())
    float_n = int((rtk["Q"] == 2).sum())

    # Ghép RTK và Single theo đúng mốc thời gian (epoch), KHÔNG cắt theo vị trí dòng.
    # RTK hay rớt epoch (mất fix do thiếu vệ tinh chung với base) còn Single thường
    # tính ra vị trí ở hầu hết epoch -> nếu cắt theo index sẽ so sai cặp điểm.
    merged = pandas.merge(
        rtk[["time", "lat", "lon"]],
        single[["time", "lat", "lon"]],
        on="time",
        suffixes=("_rtk", "_single"),
    )

    n_common = len(merged)
    if n_common == 0:
        return None

    lat_r = merged["lat_rtk"].values
    lon_r = merged["lon_rtk"].values
    lat_s = merged["lat_single"].values
    lon_s = merged["lon_single"].values

    dlat_m = (lat_r - lat_s) * DEG2M
    dlon_m = (lon_r - lon_s) * DEG2M * np.cos(np.radians((lat_r + lat_s) / 2))

    err = np.sqrt(dlat_m**2 + dlon_m**2)

    return {
        "n": n,
        "n_common": n_common,
        "fix_n": fix_n,
        "float_n": float_n,
        "fix_pct": fix_n / n * 100 if n else 0,
        "float_pct": float_n / n * 100 if n else 0,
        "err_mean": err.mean(),
        "err_max": err.max(),
        "err_std": err.std(),   # do lech chuan
        "center_lat": rtk["lat"].mean(),
        "center_lon": rtk["lon"].mean(),
    }


# VẼ BẢN ĐỒ
def build_map(rtk, single, stats):
    m = folium.Map(
        location=[stats["center_lat"], stats["center_lon"]],
        zoom_start=17,
        tiles="OpenStreetMap",
    )

    folium.PolyLine(
        rtk[["lat", "lon"]].values.tolist(),
        color="green",
        weight=2,
        tooltip="RTK",
    ).add_to(m)

    folium.PolyLine(
        single[["lat", "lon"]].values.tolist(),
        color="red",
        weight=2,
        dash_array="6 4",
        tooltip="Single",
    ).add_to(m)

    legend = f"""
    <div style="
        position: fixed;
        top: 20px;
        left: 20px;
        z-index: 9999;
        background: white;
        padding: 12px;
        border-radius: 8px;
        border: 1px solid #ccc;
        font-size: 13px;
        line-height: 1.6;
    ">
        <b>RTK vs Single</b><br>
        🟢 RTK<br>
        🔴 Single<br>
        <hr>
        Epoch trùng: {stats['n_common']}<br>
        Fix: {stats['fix_pct']:.2f}%<br>
        Float: {stats['float_pct']:.2f}%<br>
        Sai số TB: {stats['err_mean']:.3f} m<br>
        Max: {stats['err_max']:.3f} m
    </div>
    """

    m.get_root().html.add_child(folium.Element(legend))

    return m


def main():
    print("Đang đọc dữ liệu...")

    rtk = parse_pos(RTK_FILE)
    single = parse_pos(SINGLE_FILE)

    if rtk.empty or single.empty:
        print("Không đọc được dữ liệu")
        return

    stats = compute_stats(rtk, single)

    if stats is None:
        print("Không có epoch trùng thời gian giữa hai file, không thể tính sai số")
        return

    print("\n===== KẾT QUẢ =====")
    print("RTK points     :", stats["n"])
    print("Epoch trùng    :", stats["n_common"])
    print("Fix %          :", round(stats["fix_pct"], 2))
    print("Float %        :", round(stats["float_pct"], 2))
    print("Sai số TB      :", round(stats["err_mean"], 2), "m")
    print("Sai số Max     :", round(stats["err_max"], 2), "m")

    print("\nĐang vẽ bản đồ...")
    m = build_map(rtk, single, stats)

    m.save(OUTPUT_HTML)

    print("DONE! File:", OUTPUT_HTML)


if __name__ == "__main__":
    main()