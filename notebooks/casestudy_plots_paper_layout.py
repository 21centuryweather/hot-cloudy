# # Hot & Cloudy Master Plotting Script for Case Studies
# ##### Purpose: This notebook will input a date, then plot the day of conditions and the time series of the window surrounding them
# ##### Version history: Created by A.D. 07/01/2026, updated to submission version 10/04/26

# In[1]:


import numpy as np
import xarray as xr
import pandas as pd
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from pathlib import Path
from functools import partial
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from datetime import datetime
import string
from matplotlib.colors import LinearSegmentedColormap
import matplotlib.patches as mpatches


# In[15]:


# ============================================================
# SHARED COLOUR MAP — consistent across all time series panels
# Order matches: QLD, NSW, VIC, SA
# ============================================================
STATE_COLOURS = {
    "QLD": "#EB9DA2",
    "NSW": "#F0B884",
    "VIC": "#C5ACE8",
    "SA":  "#ACBBE8",
}

# Solar panel uses region codes — map to same colours
REGION_COLOURS = {
    "GBRI": "#EB9DA2",  # QLD
    "GSYD": "#F0B884",  # NSW
    "GMEL": "#C5ACE8",  # VIC
    "GADE": "#ACBBE8",  # SA
}

STATES = ["QLD", "NSW", "VIC", "SA"]


# In[3]:

def master_plot_multi(events):
    """
    Create a single figure for multiple event dates.

    Parameters
    ----------
    events : list of (datetime, list-of-states)
        Each entry is one column of synoptic maps and defines which state lines
        to highlight in the shared time-series panels for that day.


    Layout
    ------
        Row 0  : temp/MSLP/Z500 maps   — one column per event date
        Row 1  : Solar + Wind CF maps  — one column per event date
        Row 2  : Hourly 2m Temp Anomaly          (full width)
        Row 3  : Solar CF Anomaly                (full width)
        Row 4  : Wind CF by State                (full width)
        Row 5  : Demand Anomaly                  (full width)


    Time-series highlights
    ----------------------
    Instead of a single grey shaded box, each event date's 24-hour window is
    highlighted by thickening (lw=4) the lines for that date's states only.
    All other state lines are drawn thin (lw=1) throughout.  No axvspan is used.
    """

    n = len(events)

    # ------------------------------------------------------------------ #
    # Figure / GridSpec                                                    #
    # ------------------------------------------------------------------ #
    fig = plt.figure(figsize=(7 * n, 30))

    # Map rows: tight vertical spacing
    gs_maps = gridspec.GridSpec(
        2, n,
        height_ratios=[0.6, 0.6],
        hspace=0.10,
        wspace=0.20,
        top=0.78,
        bottom=0.52,
    )

    # Time-series rows: normal spacing below the maps
    gs_ts = gridspec.GridSpec(
        4, 1,
        hspace=0.50,
        top=0.5,
        bottom=0.03,
    )

    # ------------------------------------------------------------------ #
    # ROW 0 + ROW 1 — Synoptic maps (one column per date)                 #
    # ------------------------------------------------------------------ #
    # Fixed colorbar ranges — shared across all columns
    TEMP_VMIN,  TEMP_VMAX,  TEMP_STEP  = 5, 45,   5    # °C
    SOLAR_VMIN, SOLAR_VMAX, SOLAR_STEP = 0,  1020, 120  # W m⁻²

    map_axes = []  # collect axes for panel labelling
    for col, (event_dt, _) in enumerate(events):
        ax_top = fig.add_subplot(gs_maps[0, col], projection=ccrs.PlateCarree())
        ax_bot = fig.add_subplot(gs_maps[1, col], projection=ccrs.PlateCarree())
        map_axes.append((ax_top, ax_bot))

        # Pass fixed ranges so all maps share the same scale
        plot_synoptic(
            event_dt, ax_top, ax_bot,
            temp_vmin=TEMP_VMIN, temp_vmax=TEMP_VMAX, temp_step=TEMP_STEP,
            solar_vmin=SOLAR_VMIN, solar_vmax=SOLAR_VMAX, solar_step=SOLAR_STEP,
        )

        # Date label above each column (both map rows share the same date)
        ax_top.set_title(
            event_dt.strftime("%d/%m/%Y") + "\nDaily Max Temp, MSLP (contours), 500hPa GPH (--- contours)",
            fontsize=10,
        )
        ax_bot.set_title(
            event_dt.strftime("%d/%m/%Y") + "\nSolar Radiation & Wind CF",
            fontsize=10,
        )

    # ------------------------------------------------------------------ #
    # ROWS 2-5 — Shared time-series panels (full width)                   #
    # ------------------------------------------------------------------ #
    ax_temp   = fig.add_subplot(gs_ts[0])
    ax_solar  = fig.add_subplot(gs_ts[1])
    ax_wind   = fig.add_subplot(gs_ts[2])
    ax_demand = fig.add_subplot(gs_ts[3])

    # Use the first event date to define the time window
    ref_datetime = events[0][0]


    plot_solar_multi(events, ref_datetime, ax_solar)
    plot_temp_multi(events, ref_datetime, ax_temp)
    plot_wind_multi(events, ref_datetime, ax_wind)
    plot_demand_multi(events, ref_datetime, ax_demand)

    # ------------------------------------------------------------------ #
    # Panel labels
    # ------------------------------------------------------------------ #

    def _add_label(ax, letter, is_cartopy=False):
        """Place a bold letter label in the top-left corner of an axes."""
        if is_cartopy:
            ax.text(-0.04, 1.05, f"{letter})", transform=ax.transAxes,
                    fontsize=12, fontweight='bold', va='bottom', ha='right')
        else:
            ax.text(0.01, 0.99, f"{letter})", transform=ax.transAxes,
                    fontsize=12, fontweight='bold', va='top', ha='left')

    all_labels = list(string.ascii_lowercase)
    idx = 0

    # Row 0: top map axes (left to right)
    for ax_top, _ in map_axes:
        _add_label(ax_top, all_labels[idx], is_cartopy=True)
        idx += 1

    # Row 1: bottom map axes (left to right)
    for _, ax_bot in map_axes:
        _add_label(ax_bot, all_labels[idx], is_cartopy=True)
        idx += 1

    # Rows 2-5: time-series panels
    for ax_ts in [ax_temp, ax_solar, ax_wind, ax_demand]:
        _add_label(ax_ts, all_labels[idx])
        idx += 1


    return fig


# In[16]:


def plot_synoptic(event_datetime, ax_left, ax_right,
                  temp_vmin=10, temp_vmax=42, temp_step=4,
                  solar_vmin=0, solar_vmax=1020, solar_step=120):
    """
    Parameters
    ----------
    event_datetime : datetime.datetime
    ax_left  : matplotlib axis for the temperature/MSLP/Z500 panel
    ax_right : matplotlib axis for the solar + wind CF hatching panel
    temp_vmin, temp_vmax   : colorbar range for the temperature panel (°C)
    solar_vmin, solar_vmax : colorbar range for the solar panel (W m⁻²)
    """

    # -----------------------------
    # Preprocess helper
    # -----------------------------
    def _preprocess(ds, lon_bnds=None, lat_bnds=None, timesel=None):
        if timesel is not None:
            ds = ds.sel(time=timesel, method='nearest')
        if lon_bnds and lat_bnds:
            ds = ds.sel(lon=slice(*lon_bnds), lat=slice(*lat_bnds))
        return ds

    # -----------------------------
    # BARRA2 loader
    # -----------------------------
    def get_BARRA2_fields(fdate):
        fstring = fdate.strftime('%Y%m-%Y%m.nc')

        fname_msl = '/g/data/ob53/BARRA2/output/reanalysis/AUS-11/BOM/ERA5/historical/hres/BARRA-R2/v1/1hr/psl/v20250528/psl_AUS-11_ERA5_historical_hres_BOM_BARRA-R2_v1_1hr_' + fstring
        fname_u   = '/g/data/ob53/BARRA2/output/reanalysis/AUS-11/BOM/ERA5/historical/hres/BARRA-R2/v1/1hr/ua100m/v20250528/ua100m_AUS-11_ERA5_historical_hres_BOM_BARRA-R2_v1_1hr_' + fstring
        fname_v   = '/g/data/ob53/BARRA2/output/reanalysis/AUS-11/BOM/ERA5/historical/hres/BARRA-R2/v1/1hr/va100m/v20250528/va100m_AUS-11_ERA5_historical_hres_BOM_BARRA-R2_v1_1hr_' + fstring
        fname_tasmax = '/g/data/ob53/BARRA2/output/reanalysis/AUS-11/BOM/ERA5/historical/hres/BARRA-R2/v1/1hr/tasmax/v20250528/tasmax_AUS-11_ERA5_historical_hres_BOM_BARRA-R2_v1_1hr_' + fstring
        fname_zg500  = '/g/data/ob53/BARRA2/output/reanalysis/AUS-11/BOM/ERA5/historical/hres/BARRA-R2/v1/1hr/zg500/latest/zg500_AUS-11_ERA5_historical_hres_BOM_BARRA-R2_v1_1hr_' + fstring

        partial_func = partial(_preprocess, lon_bnds=lon_bnds, lat_bnds=lat_bnds, timesel=fdate)

        dmslp  = xr.open_mfdataset(fname_msl, preprocess=partial_func)
        dsu    = xr.open_mfdataset(fname_u,   preprocess=partial_func)
        dsv    = xr.open_mfdataset(fname_v,   preprocess=partial_func)
        dtmax  = xr.open_mfdataset(fname_tasmax, preprocess=partial_func)
        dzg500 = xr.open_mfdataset(fname_zg500,  preprocess=partial_func)

        return dmslp, dsu, dsv, dtmax, dzg500

    # -----------------------------
    # Himawari loader
    # -----------------------------
    times = [f"{h:02d}{m:02d}" for h in range(7) for m in range(0, 60, 10)]

    def get_date_solar(date):
        year = date.year
        month = f"{date.month:02d}"
        day = f"{date.day:02d}"

        version = "v1.0" if date <= pd.Timestamp("2019-03-31") else "v1.1"
        dir_path = Path(f"/g/data/rv74/satellite-products/arc/der/himawari-ahi/solar/p1s/{version}/{year}/{month}/{day}/")

        all_files = list(dir_path.glob("*.nc"))
        files = [f for f in all_files if any(t in f.name for t in times)]

        solar = xr.open_mfdataset(
            files,
            chunks="auto",
            concat_dim="time",
            combine="nested",
            coords="minimal",
            compat="override",
            parallel=True,
        )
        return solar.surface_global_irradiance

    # -----------------------------
    # Domain bounds
    # -----------------------------
    lon_bnds = (110, 160)
    lat_bnds = (-45, -9)

    # -----------------------------
    # Load data
    # -----------------------------
    # BARRA2 files are in UTC — convert event_datetime from AEST to UTC for selection
    event_utc = event_datetime - pd.Timedelta(hours=10)
    dmslp, dsu, dsv, dtmax, dzg500 = get_BARRA2_fields(event_utc)

    dsolar = get_date_solar(event_utc)
    dsolar = dsolar.sel(time=event_utc.strftime("%Y-%m-%dT%H:%M:%S"))

    # -----------------------------
    # Wind → capacity factor
    # -----------------------------
    dws = (dsu["ua100m"]**2 + dsv["va100m"]**2)**0.5

    def capacity_factor(W):
        W_0, W_r, W_1 = 3.5, 13, 25
        cf = (W**3 - W_0**3) / (W_r**3 - W_0**3)
        cf = cf.where(W >= W_0, 0)
        cf = cf.where(W < W_r, 1)
        cf = cf.where(W < W_1, 0)
        return cf.where(W.notnull(), np.nan)

    dcf = capacity_factor(dws)

    # -----------------------------
    # Extract fields
    # -----------------------------
    mslp  = dmslp["psl"]/100
    tmax  = dtmax["tasmax"] - 273.15
    cf    = dcf
    solar = dsolar
    zg500 = dzg500["zg500"]

    lon, lat = mslp["lon"].values, mslp["lat"].values
    lon2d, lat2d = np.meshgrid(lon, lat)

    slon, slat = solar["longitude"].values, solar["latitude"].values
    slon2d, slat2d = np.meshgrid(slon, slat)

    # -----------------------------
    # Plotting on provided axes
    # -----------------------------
    for ax in (ax_left, ax_right):
        ax.set_extent([110, 160, -45, -9])
        ax.coastlines(resolution="10m")
        ax.add_feature(cfeature.BORDERS, linestyle=":")

    # --- Panel 1: Temp + MSLP + Z500 ---
    temp_levels  = np.arange(temp_vmin,  temp_vmax  + temp_step,  temp_step)   # e.g. 10,14,18,...,42
    cf_temp = ax_left.contourf(lon2d, lat2d, tmax.values, cmap="hot_r",
                               levels=temp_levels, extend="both", alpha=0.4)
    cs1 = ax_left.contour(lon2d, lat2d, mslp.values, levels=10, colors="black", linewidths=1)
    ax_left.contour(lon2d, lat2d, zg500.values, levels=10, colors="darkgrey", linewidths=1, linestyles="--")

    ax_left.clabel(cs1, fmt="%d", inline=True, fontsize=8)
    # Title is set by the caller (master_plot_multi) so we leave it blank here
    # to avoid duplication; the caller always sets it explicitly.

    # --- Panel 2: Solar + CF hatching ---
    grey_yellow = LinearSegmentedColormap.from_list("grey_yellow", ["lightsteelblue", "#FDFD97"])
    solar_levels = np.arange(solar_vmin, solar_vmax + solar_step, solar_step)  # e.g. 0,120,240,...,1020
    cf_solar = ax_right.contourf(slon2d, slat2d, solar.values, cmap=grey_yellow,
                                 levels=solar_levels, extend="both")

    hatch_levels = [0, 0.25, 0.5, 0.75, 1.01]
    hatches = ["", "//", "///", "/////"]

    for i in range(4):
        mask = (cf.values >= hatch_levels[i]) & (cf.values < hatch_levels[i+1])
        ax_right.contourf(lon2d, lat2d, mask, levels=[0.5, 1.5], hatches=[hatches[i]], colors="none")

    ax_right.set_title("Solar Radiation & Wind CF")

    # --- Hatching legend ---
    hatch_labels = [
        "CF 0.00–0.25",
        "CF 0.25–0.50",
        "CF 0.50–0.75",
        "CF 0.75–1.00"
    ]

    hatch_handles = [
        mpatches.Patch(facecolor='white', hatch=hatches[i], label=hatch_labels[i], edgecolor='black')
        for i in range(4)
    ]

    ax_right.legend(
        handles=hatch_handles,
        title="Wind Capacity Factor",
        loc="upper left",
        frameon=True,
        fontsize=6
    )
    # Title is set by the caller (master_plot_multi).

    plt.colorbar(cf_temp, ax=ax_left, orientation='vertical', pad=0.02, shrink=0.5, label='Daily max temp (°C)')
    plt.colorbar(cf_solar, ax=ax_right, orientation='vertical', pad=0.02, shrink=0.5, label='Surface downwelling shortwave flux (W/m²)')


# In[20]:


# ============================================================
# MULTI-DATE TIME-SERIES HELPERS
# ============================================================

def _day_highlight_segments(events, all_states, state_colours, ax,
                             time_index, data_getter):
    """
    Generic helper used by all four _multi plot functions.

    Parameters
    ----------
    events      : list of (datetime, list-of-states)
    all_states  : list of all state names to plot
    state_colours : dict mapping state name → hex colour
    ax          : matplotlib axis
    time_index  : pandas DatetimeIndex or xarray time coordinate for the full window
    data_getter : callable(state) → array-like of the same length as time_index
    """
    # --- thin baseline for every state ---
    for state in all_states:
        colour = state_colours.get(state, "grey")
        ax.plot(time_index, data_getter(state),
                color=colour, lw=1, label=state)

    # --- thick overdraw for each (day, states) pair ---
    for event_dt, highlight_states in events:
        event_day  = pd.Timestamp(event_dt.date())
        day_end    = event_day + pd.Timedelta(days=1)

        if hasattr(time_index, 'values'):
            t = pd.DatetimeIndex(time_index.values)
        else:
            t = pd.DatetimeIndex(time_index)

        mask = (t >= event_day) & (t < day_end)

        for state in highlight_states:
            if state not in all_states:
                continue
            colour = state_colours.get(state, "grey")
            y = np.asarray(data_getter(state))
            ax.plot(t[mask], y[mask], color=colour, lw=4)

def plot_solar_multi(events, ref_datetime, ax):
    """
    Plots CSI (Clear Sky Index) = actual / ideal at hourly resolution.
    """
    data_dir = Path('/g/data/gb02/cd3022/hot-and-cloudy/solar-pv/GCCSA/ideal-actual')
    files    = list(data_dir.glob("*.nc"))
    datasets = []
    for file in files:
        region_name = file.stem[1:5]
        ds_reg = xr.open_dataset(file)
        ds_reg = ds_reg.expand_dims(region=[region_name])
        datasets.append(ds_reg)
    ds = xr.concat(datasets, dim='region')

    time_utc        = pd.to_datetime(ds.time.values)
    time_aest       = time_utc.tz_localize("UTC").tz_convert("Australia/Brisbane")
    time_aest_naive = time_aest.tz_localize(None)
    ds = ds.assign_coords(time=("time", time_aest_naive))
    ds = ds.where(ds['time'].dt.strftime('%H:%M') != '12:40', drop=True)

    bad_days = [np.datetime64('2019-08-12'), np.datetime64('2019-10-01'), np.datetime64('2020-09-06')]
    ds_dates = ds['time'].dt.floor('D')
    ds = ds.sel(time=ds['time'][~ds_dates.isin(bad_days)])

    rated_capacity = 219.656729124
    ds = ds.map(lambda x: x / rated_capacity)
    ds = xr.where(ds.isnull(), 0, ds)

    event_day  = pd.Timestamp(ref_datetime.date())
    start_date = event_day - pd.Timedelta(days=3)
    end_date   = event_day + pd.Timedelta(days=2) + pd.Timedelta(days=len(events) - 1)

    actual_window = ds.actual.sel(time=slice(start_date, end_date))
    ideal_window  = ds.ideal.sel(time=slice(start_date, end_date))

    # Instantaneous CSI = actual / ideal, masking nighttime where ideal == 0
    csi_hourly = actual_window / ideal_window.where(ideal_window > 0)

    # Filter to 10am–5pm AEST only
    hour = csi_hourly['time'].dt.hour
    csi_hourly = csi_hourly.sel(time=(hour >= 8) & (hour < 17))

    # Insert NaN breaks between days to prevent cross-day line connections
    time_vals = pd.DatetimeIndex(csi_hourly['time'].values)
    day_breaks = np.where(np.diff(time_vals.date))[0] + 1  # indices where the date changes

    # Build a new time index with NaN rows inserted at each day boundary
    nan_times = time_vals[day_breaks - 1] + pd.Timedelta(minutes=1)  # dummy timestamps for NaN rows
    break_da = xr.DataArray(
        np.full((len(day_breaks), len(csi_hourly.region)), np.nan),
        coords={
            'time': nan_times,
            'region': csi_hourly.region
        },
        dims=['time', 'region']
    )
    csi_hourly = xr.concat([csi_hourly, break_da], dim='time').sortby('time')

    state_to_region = {
        "QLD": "GBRI", "NSW": "GSYD", "VIC": "GMEL",
        "SA":  "GADE",
    }
    region_to_state = {v: k for k, v in state_to_region.items()}

    region_events = [
        (dt, [state_to_region[s] for s in states if s in state_to_region])
        for dt, states in events
    ]
    regions = [r for r in csi_hourly.region.values if r in REGION_COLOURS]

    def data_getter(region):
        return csi_hourly.sel(region=region).values

    _day_highlight_segments(region_events, regions, REGION_COLOURS, ax,
                            csi_hourly.time, data_getter)

    ax.set_title('Clear Sky Index (CSI): Actual / Ideal (AEST)', fontsize=12)
    ax.set_ylabel('CSI (dimensionless)')
    ax.set_xlabel('Time (AEST)')
    ax.set_ylim([0,1.1])
    ax.axhline(1.0, color='grey', linestyle='--', lw=1, label='CSI = 1 (clear sky)')
    ax.grid(True)
    ax.legend(fontsize=8, loc='upper right')


def plot_temp_multi(events, ref_datetime, ax):

    fname_his_tas = "/g/data/w42/ad1803/Hot_Cloudy/Demand/output_data/barra/tas/tas_barra-c2_hourly_1984-2024_NEM_pop_dens_mask_*.nc"
    dhis_tas = xr.open_mfdataset(fname_his_tas)
    tas = dhis_tas['tas']
    tas["time"] = [i + pd.DateOffset(hours=10) for i in tas.time.values]
    tas = tas.sortby("time")
    tas = tas.sel(time=tas.time.dt.dayofyear != 366)

    clim = xr.open_dataset("/g/data/w42/ad1803/Hot_Cloudy/Case_Studies/Output_data/climatology_15day_window.nc")['tas']
    clim_aligned = clim.sel(
        doy=tas.time.dt.dayofyear,
        hour=tas.time.dt.hour
    ).drop_vars(['doy', 'hour'])
    tas_anom = tas - clim_aligned

    event_day  = pd.Timestamp(ref_datetime.date())
    start_date = event_day - pd.Timedelta(days=3)
    end_date   = event_day + pd.Timedelta(days=2) + pd.Timedelta(days=len(events) - 1)
    tas_anom_window = tas_anom.sel(time=slice(start_date, end_date))

    regions = [r for r in STATE_COLOURS if r in tas_anom_window.region.values]

    def data_getter(state):
        return tas_anom_window.sel(region=state).values

    _day_highlight_segments(events, regions, STATE_COLOURS, ax,
                            tas_anom_window.time, data_getter)

    ax.set_title("Hourly 2m Temp Anomaly vs 15-day DOY–Hour Climatology (AEST)", fontsize=12)
    ax.set_xlabel("Time (AEST)")
    ax.set_ylabel("Temperature Anomaly (°C)")
    ax.axhline(0, color='dimgrey', linestyle='-', lw=3)
    ax.grid(True)
    ax.legend(fontsize=8)
    #ax.legend([QLD, NSW, VIC, SA], ['QLD', 'NSW', 'VIC', 'SA'])




def plot_wind_multi(events, ref_datetime, ax):

    fname_barra_cf = "/g/data/w42/ad1803/Hot_Cloudy/Case_Studies/Output_data/cf100m_by_state_*.nc"
    dcf = xr.open_mfdataset(fname_barra_cf)
    dcf["time"] = [i + pd.DateOffset(hours=10) for i in dcf.time.values]
    dcf = dcf.sortby("time")

    event_day  = pd.Timestamp(ref_datetime.date())
    start_date = event_day - pd.Timedelta(days=3)
    end_date   = event_day + pd.Timedelta(days=2) + pd.Timedelta(days=len(events) - 1)
    cf_subset  = dcf.sel(time=slice(start_date, end_date))

    time_index = pd.DatetimeIndex(cf_subset.time.values)

    def data_getter(state):
        return cf_subset[state].values

    _day_highlight_segments(events, STATES, STATE_COLOURS, ax,
                            time_index, data_getter)

    ax.set_title("Wind Capacity Factor by State (AEST)")
    ax.set_xlabel("Time (AEST)")
    ax.set_ylabel("Wind Capacity Factor")
    ax.legend(fontsize=8)
    ax.grid(True)


def plot_demand_multi(events, ref_datetime, ax):

    fname_demand = "/g/data/w42/ad1803/Hot_Cloudy/Demand/input_data/hourly_demand_20090701-20231230.csv"
    df = pd.read_csv(fname_demand)
    df["SETTLEMENTDATE"] = pd.to_datetime(df["SETTLEMENTDATE"])
    df = df.set_index("SETTLEMENTDATE")
    df["hour"] = df.index.hour

    clim_mean = df.groupby("hour")[STATES].mean()
    clim_std  = df.groupby("hour")[STATES].std()

    event_day  = pd.Timestamp(ref_datetime.date())
    start_date = event_day - pd.Timedelta(days=3)
    end_date   = event_day + pd.Timedelta(days=2) + pd.Timedelta(days=len(events) - 1)

    demand_subset = df.loc[start_date:end_date].copy()
    hours         = demand_subset.index.hour

    demand_norm = pd.DataFrame(
        (demand_subset[STATES].values - clim_mean.loc[hours].values) / clim_std.loc[hours].values,
        index=demand_subset.index,
        columns=STATES
    )

    time_index = demand_norm.index

    def data_getter(state):
        return demand_norm[state].values

    _day_highlight_segments(events, STATES, STATE_COLOURS, ax,
                            time_index, data_getter)

    ax.set_title("Electricity Demand by State — Z-score Normalised by Hour-of-Day (Full Record, AEST)")
    ax.set_xlabel("Time (AEST)")
    ax.set_ylabel("Demand Anomaly (σ)")
    ax.legend(fontsize=8)
    ax.axhline(0, color='dimgrey', linestyle='-', lw=3)
    ax.grid(True)


# In[10]:


# In[21]:


# ============================================================
# EXECUTION — 3-date hot & cloudy case study
# ============================================================
events = [
    (datetime(2021, 2, 11, 12), ["SA", "VIC"]),
    (datetime(2021, 2, 12, 12), ["NSW"]),
    (datetime(2021, 2, 13, 12), ["QLD"]),
]

fig = master_plot_multi(events)

# Build a filename from the dates
date_str = "_".join(dt.strftime("%Y%m%d") for dt, _ in events)
filename = f"FinPaper_Casestudy_multi_{date_str}.png"


fig.savefig(f"/g/data/w42/ad1803/Hot_Cloudy/Case_Studies/Plots/{filename}", dpi=200)







