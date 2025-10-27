import glob
import numpy as np
import pandas as pd
import xarray as xr
import scipy
import intake
import datetime as dt
import argparse
import dask.array as da
import metpy.calc as mpcalc
from metpy import units
from dask.distributed import Client, progress
import skimage
import xesmf
import os

def load_era5_variable(vnames,t1,t2,lon_slice,lat_slice,chunks="auto"):

    '''
    Load era5 data using the NCI intake catalog

    Input
    vname: list of names of era5 variables
    t1: start time in %Y-%m-%d %H:%M"
    t1: end time in %Y-%m-%d %H:%M"
    lat_slice: a slice to restrict lat domain
    lon_slice: a slice to restrict lon domain

    Output:
    xarray dataset
    '''

    #Set up times to search within catalog
    data_catalog = get_intake_cat_era5()
    time_starts = pd.date_range(pd.to_datetime(t1).replace(day=1),t2,freq="MS").strftime("%Y%m%d").astype(int).values
    time_ends = [(t + dt.timedelta(days=32)).replace(day=1) - dt.timedelta(days=1) for t in pd.to_datetime(time_starts,format="%Y%m%d")]
    times = [str(t1) + "-" + t2.strftime("%Y%m%d") for t1,t2 in zip(time_starts,time_ends)]

    #Load the data using intake
    out = dict.fromkeys(vnames)
    for vname in vnames:
        ds = data_catalog.search(variable=vname,
                                product="era5-reanalysis",
                                time_range=times).\
                                    to_dask(cdf_kwargs={"chunks":chunks}).\
                                        sel(time=slice(t1,t2))
        ds = ds.isel(latitude=slice(None,None,-1))
        ds["longitude"] = (ds.longitude % 360)
        ds = ds.sortby("longitude")    
        ds = ds.rename({"longitude":"lon","latitude":"lat"}).sel(lon=lon_slice, lat=lat_slice)
        out[vname] = ds
        
    return out

def get_intake_cat_era5():

    '''
    Return the intake catalog for era5
    '''

    #See here: https://opus.nci.org.au/pages/viewpage.action?pageId=264241965
    data_catalog = intake.open_esm_datastore("/g/data/rt52/catalog/v2/esm/catalog.json")

    return data_catalog

def load_barra_variable(vname, t1, t2, domain_id, freq, lat_slice, lon_slice, chunks="auto", smooth=False, sigma=2, smooth_axes=None):

    """
    Load a variable from the BARRA dataset.

    Parameters
    ----------
    vname : str
        Name of BARRA variable to load.
    t1 : str
        Start time in "%Y-%m-%d %H:%M".
    t2 : str
        End time in "%Y-%m-%d %H:%M".
    domain_id : str
        BARRA domain, either "AUS-04", "AUST-11" or "AUS-11".
    freq : str
        Frequency string (e.g., "1h").
    lat_slice : slice or array-like
        Slice or indices to restrict latitude domain.
    lon_slice : slice or array-like
        Slice or indices to restrict longitude domain.
    chunks : dict or str, optional
        Chunking for xarray open_mfdataset (default is "auto").
    smooth : bool, optional
        If True, smooth the data using a Gaussian filter.
    sigma : float, optional
        Sigma value for the Gaussian filter if smoothing.
    smooth_axes : iterable, optional
        Axes to smooth over if smoothing.

    Returns
    -------
    da : xarray.DataArray
        The requested variable, optionally smoothed.

    """

    if domain_id in ["AUST-04"]:
        model = "BARRA-C2"
    elif domain_id in ["AUST-11","AUS-11"]:
        model = "BARRA-R2"
    else:
        raise ValueError("Invalid domain id")

    #data_catalog = get_intake_cat_barra()
    times = pd.date_range(pd.to_datetime(t1).replace(day=1),t2,freq="MS").strftime("%Y%m").astype(int).values
    files = [glob.glob("/g/data/ob53/BARRA2/output/reanalysis/"\
                    +domain_id+"/BOM/ERA5/historical/hres/"+model+\
                        "/v1/"+freq+"/"+vname+"/latest/"+\
                            vname+"_"+domain_id+"_*_"+str(t)+"-*.nc") for t in times]
    da = xr.open_mfdataset(
        np.concatenate(files),
        chunks=chunks).\
                sel(lon=lon_slice, lat=lat_slice, time=slice(t1,t2))[vname]
    #da = data_catalog.search(
    #    variable_id=vname,
    #    domain_id=domain_id,
    #    freq=freq,
    #    start_time=times)\
    #        .to_dask(cdf_kwargs={"chunks":chunks}).\
    #            sel(lon=lon_slice, lat=lat_slice, time=slice(t1,t2))[vname]
    
    #Optional smoothing
    da = da.assign_attrs({"smoothed":smooth})
    if smooth:

        if smooth_axes is not None:
            for ax in smooth_axes:
                chunks[ax] = -1
            smooth_axes = (np.where(np.in1d(da.isel(time=0).dims,smooth_axes))[0])
        else:
            chunks["lon"] = -1
            chunks["lat"] = -1

        da = da.map_blocks(
            gaussian_filter_time_slice,
            kwargs={"sigma":sigma,"axes":smooth_axes},
            template=da
        )
        da = da.assign_attrs({"gaussian_smoothing_sigma":sigma})
        
    return da

def gaussian_filter_time_slice(time_slice,sigma,axes):
    """
    Apply a gaussian filter to a time slice of data. For use with map_blocks
    """
    #out_ds = xr.DataArray(scipy.ndimage.gaussian_filter(time_slice.squeeze(), sigma, axes=axes),
    #                      dims=time_slice.squeeze().dims, coords=time_slice.squeeze().coords)
    out_ds = xr.DataArray(scipy.ndimage.gaussian_filter(
        time_slice.isel(time=0), sigma, axes=axes
        ),dims=time_slice.isel(time=0).dims, coords=time_slice.isel(time=0).coords)
    out_ds = out_ds.expand_dims("time")
    out_ds["time"] = time_slice.time
    return out_ds

def calc_mag_theta(theta):

    """
    Calculate the magnitude of the horizontal potential temperature gradient (in units of K / 100 km)
    """

    #Set up lat lon array and delta x/y array (lat lon distances in km)
    x,y = np.meshgrid(theta.lon,theta.lat)
    dx, dy = mpcalc.lat_lon_grid_deltas(x,y)

    dx = xr.DataArray(np.array(dx),dims=["lat","lon"],coords={"lat":theta.lat.values, "lon":theta.lon.values[0:-1]}).\
            interp({"lon":theta.lon,"lat":theta.lat},method="linear",kwargs={"fill_value":"extrapolate"}).\
            chunk({"lat":theta.chunksizes["lat"][0], "lon":theta.chunksizes["lon"][0]})
    dy = xr.DataArray(np.array(dy),dims=["lat","lon"],coords={"lat":theta.lat.values[0:-1], "lon":theta.lon.values}).\
            interp({"lon":theta.lon,"lat":theta.lat},method="linear",kwargs={"fill_value":"extrapolate"}).\
            chunk({"lat":theta.chunksizes["lat"][0], "lon":theta.chunksizes["lon"][0]})

    dx = xr.where(dx==0,1,dx)

    #Calculate the magnitude of the horizontal temperature gradient (in units of K / 100 km)
    ddy_theta = (xr.DataArray(da.gradient(theta,axis=t.get_axis_num("lat")), dims=theta.dims, coords=theta.coords) / dy)
    ddx_theta = (xr.DataArray(da.gradient(theta,axis=t.get_axis_num("lon")), dims=theta.dims, coords=theta.coords) / dx)

    mag_theta = (np.sqrt( ddy_theta**2 + ddx_theta**2) * 1000 * 100)    

    return mag_theta

def filter_time_slice(time_slice):
    """
    Apply a gaussian filter to a time slice of data. For use with map_blocks
    """
    #out_ds = xr.DataArray(scipy.ndimage.gaussian_filter(time_slice.squeeze(), sigma, axes=axes),
    #                      dims=time_slice.squeeze().dims, coords=time_slice.squeeze().coords)
    out_ds = xr.DataArray(
        skimage.morphology.remove_small_objects(skimage.measure.label(time_slice.squeeze())>0,8,connectivity=2)
        ,dims=time_slice.isel(time=0).dims, coords=time_slice.isel(time=0).coords)
    out_ds = out_ds.expand_dims("time")
    out_ds["time"] = time_slice.time
    return out_ds    

if __name__ == "__main__":

    # Set up the Dask client
    client = Client(scheduler_file=os.environ["DASK_PBS_SCHEDULER"])
    #client = Client()

    # Argument parser for the script
    parser = argparse.ArgumentParser(description="Calculate the magnitude of the horizontal potential temperature gradient at 850 hPa from ERA5, BARRA-R and BARRA-C data.")
    parser.add_argument("t1", type=str, help="Start time (Y-m-d H:M)")
    parser.add_argument("t2", type=str, help="End time (Y-m-d H:M)")
    args = parser.parse_args()
    t1 = args.t1
    t2 = args.t2

    #Set up interpolation grid and settings
    interp_lon = np.arange(110,160,0.75)
    interp_lat = np.arange(-45,-9.25,0.75)
    ds_out = xr.Dataset({
        "lat": (["lat"], interp_lat, {"units": "degrees_north"}),
        "lon": (["lon"], interp_lon, {"units": "degrees_east"}),
    })
    p=850
    mag_theta_thresh = 4 #K / 100 km

    ########
    #ERA5
    ########

    #Load data
    def preprocess(ds):
        return ds.sel(level=p).sel(time=slice(t1,t2),latitude=slice(-5,-50),longitude=slice(100,160))
    t1_yy=pd.to_datetime(t1).strftime("%Y")
    t1_yymm = pd.to_datetime(t1).strftime("%Y%m")
    t=xr.open_mfdataset(f"/g/data/rt52/era5/pressure-levels/reanalysis/t/{t1_yy}/t_era5_oper_pl_{t1_yymm}*.nc",
            preprocess=preprocess)["t"].chunk({"latitude":-1,"longitude":-1})
    t = t.rename({"latitude":"lat","longitude":"lon"})

    #Calculate potential temperature and interpolate to 0.75 degree grid
    theta = mpcalc.potential_temperature(p * units.units.hectopascal, t).metpy.dequantify() 
    #theta = theta.interp(lat=interp_lat,lon=interp_lon,method="linear")
    print("ERA5 re-gridding...")
    regridder = xesmf.Regridder(theta, ds_out, "conservative")
    theta = regridder(theta, keep_attrs=True)

    #Calculate magnitude of potential temperature and apply object filter
    mag_theta = calc_mag_theta(theta)
    mask_era5 = mag_theta>mag_theta_thresh
    mask_era5 = mask_era5.map_blocks(filter_time_slice,
                    template=mask_era5)

    #Attributes
    mask_era5.name = "era5_front_850hPa"
    mask_era5.attrs["description"] = f"Fronts identified from ERA5, BARRA-R and BARRA-C potential temperature gradient at 850 hPa using a threshold of {mag_theta_thresh} K / 100 km. All data is first interpolated to a 0.75 degree grid. Objects smaller than 8 grid points in area are removed."
    mask_era5.attrs["interpolation"] = "Conservative regridding to 0.75 degree grid using xESMF"

    ##########
    #BARRA-R
    ##########
    domain_id = "AUS-11"
    freq = "1hr"
    lat_slice = slice(-50,-5)
    lon_slice = slice(100,170)
    chunks = {"time":{},"lat":-1,"lon":-1}
    smooth = False
    sigma=None
    
    ta = load_barra_variable("ta"+str(p),t1,t2,domain_id,freq,lat_slice,lon_slice,chunks=chunks,smooth=smooth,sigma=sigma)
    theta = mpcalc.potential_temperature(
        p * units.units.hectopascal, ta).metpy.dequantify()
    print("BARRA-R re-gridding...")
    regridder = xesmf.Regridder(theta, ds_out, "conservative")
    theta = regridder(theta, keep_attrs=True).chunk({"time":1})

    mag_theta = calc_mag_theta(theta)
    mask_barra_r = mag_theta>mag_theta_thresh
    mask_barra_r = mask_barra_r.map_blocks(filter_time_slice,
                    template=mask_barra_r)
    barra_r_missing = mag_theta.isnull().isel(time=0)

    #Attributes
    mask_barra_r.name = "barra_r_front_850hPa"
    mask_barra_r.attrs["description"] = f"Fronts identified from BARRA-R potential temperature at 850 hPa using a threshold of {mag_theta_thresh} K / 100 km. BARRA-R data first interpolated to a 0.75 degree grid. Objects smaller than 8 grid points in area (around 50,000 km**2) are removed."
    barra_r_missing.name = "barra_r_missing"
    barra_r_missing.attrs["description"] = "Missing data mask for BARRA-R potential temperature at 850 hPa."

    ##########
    #BARRA-C
    ##########
    domain_id = "AUST-04"
    freq = "1hr"
    lat_slice = slice(-50,-5)
    lon_slice = slice(100,170)
    chunks = {"time":{},"lat":-1,"lon":-1}
    smooth = False
    sigma=None
    
    ta = load_barra_variable("ta"+str(p),t1,t2,domain_id,freq,lat_slice,lon_slice,chunks=chunks,smooth=smooth,sigma=sigma)
    theta = mpcalc.potential_temperature(
        p * units.units.hectopascal, ta).metpy.dequantify()
    print("BARRA-C re-gridding...")
    regridder = xesmf.Regridder(theta, ds_out, "conservative")
    theta = regridder(theta, keep_attrs=True).chunk({"time":1})    

    mag_theta = calc_mag_theta(theta)
    mask_barra_c = mag_theta>mag_theta_thresh
    mask_barra_c = mask_barra_c.map_blocks(filter_time_slice,
                    template=mask_barra_c)
    barra_c_missing = mag_theta.isnull().isel(time=0)

    #Attributes
    mask_barra_c.name = "barra_c_front_850hPa"
    mask_barra_c.attrs["description"] = f"Fronts identified from BARRA-C potential temperature at 850 hPa using a threshold of {mag_theta_thresh} K / 100 km. BARRA-C data first interpolated to a 0.75 degree grid. Objects smaller than 8 grid points in area (around 50,000 km**2) are removed."
    barra_c_missing.name = "barra_c_missing"
    barra_c_missing.attrs["description"] = "Missing data mask for BARRA-C potential temperature at 850 hPa."

    #Combine and save
    out = xr.merge([mask_era5,mask_barra_r,mask_barra_c,barra_r_missing,barra_c_missing])
    out.to_netcdf("/g/data/gb02/ab4502/hot_cloudy/fronts/front_"+pd.to_datetime(t1).strftime("%Y%m%d")+"_"+pd.to_datetime(t2).strftime("%Y%m%d")+".nc",compute=True)
    out = out.persist()
    progress(out)

    client.close()