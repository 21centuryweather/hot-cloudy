import xarray as xr
from pathlib import Path
import numpy as np
import pandas as pd
import datetime as dt
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from IPython.display import Image

def load_demand_data():
    path = "/g/data/gb02/ad1803/Hot & Cloudy/Demand Data/"
    hot_demand_days = xr.open_dataset(path+"hot_high_demand_days.nc")
    hot_low_demand_days = xr.open_dataset(path+"hot_low_demand_days.nc")
    return hot_demand_days, hot_low_demand_days

def load_nemosis(path):
    df = pd.read_csv(path,parse_dates=True,index_col=0)
    return df

def load_stn_data(state,stn_no,t1,t2):

    assert state in ["VIC","NSW-ACT","QLD","SA","TAS-ANT"], "State must be one of: VIC, NSW-ACT, QLD, SA, TAS-ANT"

    f = xr.open_mfdataset("/g/data/ng72/ab4502/BoM_data_202409/half_hourly_data_netcdf/AWS-data-"+state+".nc")
    t = pd.to_datetime(f.time)
    f["time"] = t.tz_localize("UTC").tz_convert("Australia/Melbourne").tz_localize(None)
    return f.sel(station=(f.bmid.values==stn_no),time=slice(t1,t2)).temp.squeeze().persist()

def load_cloud():

    data_dir = Path('/g/data/gb02/cd3022/hot-and-cloudy/solar-pv/GCCSA/ideal-actual')
    files = list(data_dir.glob("*.nc"))
    datasets = []
    
    for file in files:
        region_name = file.stem[1:5]
        ds_reg = xr.open_dataset(file)
        ds_reg = ds_reg.expand_dims(region=[region_name])
    
        datasets.append(ds_reg)
    
    ds = xr.concat(datasets, dim='region')

    # Change times to AEST
    time_utc = pd.to_datetime(ds.time.values)
    time_aest = time_utc.tz_localize("UTC").tz_convert("Australia/Brisbane")
    time_aest_naive = time_aest.tz_convert("Australia/Brisbane").tz_localize(None)
    ds = ds.assign_coords(time=("time", time_aest_naive))
    
    ds = ds.where(ds['time'].dt.strftime('%H:%M') != '12:40', drop=True)
    
    bad_days = [
        np.datetime64('2019-08-12'),
        np.datetime64('2019-10-01'),
        np.datetime64('2020-09-06'),
        
    ]
    ds_dates = ds['time'].dt.floor('D')
    good_time_mask = ~ds_dates.isin(bad_days)
    ds = ds.sel(time=ds['time'][good_time_mask])
    
    rated_capacity = 219.656729124
    ds = ds.apply(lambda x: x / rated_capacity)
    
    #ds = xr.where(ds.isnull(), 0, ds)

    return ds

def load_cloud_gccsa():

    file_path = Path('/g/data/gb02/cd3022/hot-and-cloudy/solar-pv/GCCSA/')
    
    files = list(file_path.glob(f"*.nc"))
    ds = xr.open_mfdataset(files, combine='nested')

    ds = ds.where(ds['time'].dt.strftime('%H:%M') != '12:40', drop=True)

    bad_days = [
        np.datetime64('2019-08-12'),
        np.datetime64('2019-10-01'),
        np.datetime64('2020-09-06'),
        
    ]
    ds_dates = ds['time'].dt.floor('D')
    good_time_mask = ~ds_dates.isin(bad_days)
    ds = ds.sel(time=ds['time'][good_time_mask])

    # Rated capacity taken from sandia_modules['Canadian_Solar_CS5P_220M___2009_'], solar panel used in pvlib system,
    # using the calculation rated_capacity = module.loc['Impo'] * module.loc['Vmpo']
    rated_capacity = 219.656729124
    ds = ds.apply(lambda x: x / rated_capacity) # raw data can be used for load duration curves, before morning/evening data is removed in "clip_dusk_dawn"

    ds = xr.where(ds.isnull(), 0, ds)

    return ds

def plot_ts(date, cloud, demand, stn_data, t1, t2):

    plt.figure(figsize=[12,4])
    
    ax=plt.axes()
    
    l1=ax.plot(
        pd.DatetimeIndex(cloud.sel(time=np.in1d(cloud.time.dt.date,date)).time),
        cloud.sel(time=np.in1d(cloud.time.dt.date,date)).actual,
        color="grey")
    l2=ax.plot(
        cloud.sel(time=np.in1d(cloud.time.dt.date,date)).time,
        cloud.groupby("time.time").mean().actual,
        color="grey",ls=":",label="Average profile")
    
    plt.ylim([-0.05,1])
    
    ax2=ax.twinx()
    
    
    l3=ax2.plot(
        demand.loc[slice(t1,t2)].index,
        demand.loc[slice(t1,t2)].values,
        color="tab:blue")

    
    
    myFmt = mdates.DateFormatter('%Y-%m-%d %H:%M')
    ax.xaxis.set_major_formatter(myFmt)
    ax.tick_params("x",rotation=20)
    
    ax.set_xlabel("Time (LT)")
    ax.set_ylabel("Capacity factor")
    
    ax.grid(ls=":")

    ax2.set_ylabel("Total demand (MW)")

    ax3 = ax.twinx()
    l5=stn_data.sel(time=slice(t1,t2)).plot(color="tab:red")
    ax3.tick_params("y",pad=60)

    ax2.set_ylim([demand.min() - 100,demand.max() + 100])
    ax3.set_ylim([stn_data.min().values,stn_data.max().values])

    plt.legend([l1[0],l2[0],l3[0],l5[0]],
               ["Solar capacity factor","Average capacity factor (2015-2025)","Total demand","Temp at airport."],
              ncols=3,bbox_to_anchor=(1,-0.3))    


def plot_ausweathernews_mslp(date):
    if date.year > 2020:
        url = "https://www.australianweathernews.com/archives/mslanal/"+date.strftime("%Y")[2:]+date.strftime("%m%d06")+".gif"
    else:
        url = "https://www.australianweathernews.com/archives/mslanal/"+date.strftime("%Y")+"/"+date.strftime("%Y")[2:]+date.strftime("%m%d06")+".gif"
    try:
        return Image(url)
    except:
        print("MSLP not available")    

def plot_ausweathernews_sat(date):
    if (date.year > 2020):
        url = "https://www.australianweathernews.com/archives/satellite/BoM--irenh/IDE00134."+date.strftime("%Y%m%d0530")+".jpg"
    elif (date.year <= 2020) & (date.year >= 2017):
        url = "https://www.australianweathernews.com/archives/satellite/BoM--irenh/"+date.strftime("%Y")+"/IDE00134."+date.strftime("%Y%m%d0530")+".jpg"
    else:
        url = "https://www.australianweathernews.com/archives/satellite/BoM--irenh/"+date.strftime("%Y")+"/IDE00035."+date.strftime("%Y%m%d0530")+".jpg"
    try:
        return Image(url)
    except:
        print("Satellite not available")               