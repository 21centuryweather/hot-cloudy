import xarray as xr
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import mapping
import matplotlib.pyplot as plt
import re
# qsub -I -q normal -P er8 -l walltime=2:00:00,ncpus=24,mem=120GB,jobfs=100MB,storage=gdata/xp65+gdata/er8+gdata/ob53+gdata/rt52+gdata/rv74+gdata/su28
root_dir = '/home/548/cd3022/repos/hot-cloudy' # change for your own directory

# PREPARE DATA
ds = xr.open_zarr("/g/data/su28/himawari-ahi/cloud/ct/aus_regional_domain/S_NWC_CT_HIMA08_HIMA-N-NR.zarr")
ct = ds.ct
cumuliform = ds.ct_cumuliform
ct.rio.set_spatial_dims(
    x_dim='lon',
    y_dim='lat',
    inplace=True
)
cumuliform.rio.set_spatial_dims(
    x_dim='lon',
    y_dim='lat',
    inplace=True
)
ct.rio.write_crs('EPSG:4326', inplace=True)
cumuliform.rio.write_crs('EPSG:4326', inplace=True)

gdf = gpd.read_file('/g/data/er8/users/cd3022/data/boundary_files/GCCSA/GCCSA_2021_AUST_GDA2020.shp')


### CT NAME CODES ###

comment_ct = ds.ct.attrs['comment']
comment_cumuliform = ds.ct_cumuliform.attrs['comment']

# Use regex to extract values and labels
matches_ct = re.findall(r'(\d+):\s+([^;]+)', comment_ct)
matches_cumuliform = re.findall(r'(\d+):\s+([^;]+)', comment_cumuliform)

# Convert to dictionary
category_dict_ct = {int(num): desc.strip() for num, desc in matches_ct}
category_dict_cumuliform = {int(num): desc.strip() for num, desc in matches_cumuliform}


### HOT+CLOUDY EVENT DATES ###

df = pd.read_csv(root_dir + '/hot_cloudy_2015_2024/event_dates_csi0p5_thourly90_counts.csv')
df_null = pd.read_csv(root_dir + '/hot_cloudy_2015_2024/null_event_dates_csi0p5_thourly90_nhours7.csv')

regions = [
    'GMEL',
    'GSYD',
    'GADE',
    'GBRI'
]
for reg in regions:

    df_reg = df[df['region'].str.contains(reg)].reset_index()
    df_reg_null = df_null[df_null['region'].str.contains(reg)].reset_index()
    dates_reg = df_reg.time
    dates_reg_null = df_reg_null.time

    gdf_reg = gdf[gdf['GCC_CODE21'].str.contains(reg)]
    

    # CLOUD TYPE AND CUMULIFORM DURING EVENTS
    dates_ct = []
    dates_cumuliform = []
    for date in dates_reg:
        cloud_types = ct.sel(time=slice(date + 'T0000', date + 'T0650'))
        dates_ct.append(cloud_types)

        cloud_cumuliform = cumuliform.sel(time=slice(date + 'T0000', date + 'T0650'))
        dates_cumuliform.append(cloud_cumuliform)
    dates_ct = xr.concat(dates_ct, dim='time')
    dates_cumuliform = xr.concat(dates_ct, dim='time')

    # SAME BUT DURING NULL EVENTS
    dates_ct_null = []
    dates_cumuliform_null = []
    for date in dates_reg_null:
        cloud_types = ct.sel(time=slice(date + 'T0000', date + 'T0650'))
        dates_ct_null.append(cloud_types)

        cloud_cumuliform = cumuliform.sel(time=slice(date + 'T0000', date + 'T0650'))
        dates_cumuliform_null.append(cloud_cumuliform)
    dates_ct_null = xr.concat(dates_ct_null, dim='time')
    dates_cumuliform_null = xr.concat(dates_ct_null, dim='time')


    reg_clouds = dates_ct.rio.clip(
        gdf_reg.geometry.apply(mapping),
        gdf_reg.crs,
        drop=True
    )
    reg_cumuliform = dates_cumuliform.rio.clip(
        gdf_reg.geometry.apply(mapping),
        gdf_reg.crs,
        drop=True
    )
    reg_clouds_null = dates_ct_null.rio.clip(
        gdf_reg.geometry.apply(mapping),
        gdf_reg.crs,
        drop=True
    )
    reg_cumuliform_null = dates_cumuliform_null.rio.clip(
        gdf_reg.geometry.apply(mapping),
        gdf_reg.crs,
        drop=True
    )
    # PLOT CT & CUMULIFORM
    fig, ax = plt.subplots(nrows=2, ncols=1, constrained_layout=True, figsize = (10,10))
    ax[0].hist(
        reg_clouds.values.flatten(),
        bins=np.arange(1, 16) - 0.5,
        edgecolor='black',
        density=True,
        alpha=0.6,
        label='Event'
        )
    ax[0].hist(
        reg_clouds_null.values.flatten(),
        bins=np.arange(1, 16) - 0.5,
        edgecolor='black',
        density=True,
        alpha=0.6,
        label='Null event'
        )
    ax[0].set_xticks(list(category_dict_ct.keys()))
    ax[0].set_xticklabels(list(category_dict_ct.values()), rotation=30, ha='right')
    ax[0].legend()

    ax[1].hist(
        reg_cumuliform.values.flatten(),
        bins=np.arange(1, 7) - 0.5,
        edgecolor='black',
        density=True,
        alpha=0.6,
        label='Event'
        )
    ax[1].hist(
        reg_cumuliform_null.values.flatten(),
        bins=np.arange(1, 7) - 0.5,
        edgecolor='black',
        density=True,
        alpha=0.6,
        label='Null event'
        )
    ax[1].set_xticks(list(category_dict_cumuliform.keys()))
    ax[1].set_xticklabels(list(category_dict_cumuliform.values()), rotation=30, ha='right')

    fig.supylabel('frequency')
    fig.suptitle(reg, fontsize=20)
    plt.savefig(f'{root_dir}/figs/{reg}_event_ct_histogram.png')
    plt.close(fig)