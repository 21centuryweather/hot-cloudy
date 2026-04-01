library(lubridate)
library(ggplot2)
library(tidyverse)
library(maps)
library(sf)
library(stringr)
library(patchwork)
library(tibble)

# =============================================================================
# Directories and files
# =============================================================================
base_dir <- "hot-cloudy"

data_dir <- file.path(base_dir, "data")
events_dir <- file.path(base_dir, "data")
copula_dir <- file.path(base_dir, "data")
demand_dir <- file.path(base_dir, "data")
shapefile_dir <- file.path(base_dir, "data/shapefiles")
plot_dir <- file.path(base_dir, "figs")

gccsa_shp <- file.path(shapefile_dir, "GCCSA_2021_AUST_GDA2020.shp") 
transmission_shp <- file.path(shapefile_dir, "Transmission.shp") 

hc_hours_file <- file.path(events_dir, "event_times_csi0p5_thourly90.csv")
null_hours_file <- file.path(events_dir, "null_event_times_csi0p5_thourly90.csv")
hc_days_file <- file.path(events_dir, "event_dates_csi0p5_thourly90_counts.csv")
null_days_file <- file.path(events_dir, "null_event_dates_csi0p5_thourly90_nhours7.csv")
copula_file <- file.path(copula_dir, "pnullevent_hour_day.csv") 
demand_file <- file.path(demand_dir, "hourly_demand_20090701-20241230.csv") #

if (!dir.exists(plot_dir)) dir.create(plot_dir, recursive = TRUE)

# =============================================================================
# Settings
# =============================================================================
regions <- c("GBRI", "GSYD", "GMEL", "GADE")
years <- 2015:2024
months <- c(11, 12, 1, 2, 3, 4)
solar_hours <- 10:16

event_hour_levels <- c("Hot-Cloudy hour", "Hot-Sunny hour", "No-Event hour")
event_day_levels <- c("Hot-Cloudy day", "Hot-Sunny day", "No-Event day")

region_cols <- c(
  "GBRI" = "#EB9DA2",
  "GSYD" = "#F0B884",
  "GMEL" = "#BBEBB5",
  "GADE" = "#ACBBE8"
)

fill_vals <- c(
  "Hot-Cloudy hour" = "#7f0000",
  "Hot-Sunny hour" = "orange",
  "No-Event hour" = "lightgrey"
)

fill_day_vals <- c(
  "Hot-Cloudy day" = "#7f0000",
  "Hot-Sunny day" = "orange",
  "No-Event day" = "lightgrey"
)

transmission_col <- "#5B2C6F"

# =============================================================================
# Helpers
# =============================================================================
load_cloud <- function(region, keep_hours = TRUE) {
  out <- vector("list", length(years))

  for (i in seq_along(years)) {
    year_i <- years[i]
    cloud_file <- file.path(data_dir, paste0("Carl_Cloud_CSI_", region, "_", year_i, "_hourly_mean.csv"))

    cloud_df <- read.csv(cloud_file) %>%
      mutate(time = ymd_hms(time, tz = "Australia/Brisbane")) %>%
      filter(month(time) %in% months)

    if (keep_hours) {
      cloud_df <- cloud_df %>% filter(hour(time) %in% solar_hours)
    }

    out[[i]] <- cloud_df %>% rename(x = CSI)
  }

  bind_rows(out)
}

load_temperature <- function(region, keep_hours = TRUE) {
  out <- vector("list", length(years))

  for (i in seq_along(years)) {
    year_i <- years[i]
    tas_file <- file.path(data_dir, paste0("Alex_tas_", region, "_", year_i, "_AEST_C.csv"))

    tas_df <- read.csv(tas_file) %>%
      mutate(time = ymd_hms(time, tz = "Australia/Brisbane")) %>%
      filter(month(time) %in% months)

    if (keep_hours) {
      tas_df <- tas_df %>% filter(hour(time) %in% solar_hours)
    }

    out[[i]] <- tas_df %>% rename(y = tas)
  }

  bind_rows(out)
}

load_cloud_temperature <- function(region, keep_hours = TRUE) {
  cloud_df <- load_cloud(region, keep_hours = keep_hours)
  tas_df <- load_temperature(region, keep_hours = keep_hours)

  merge(cloud_df, tas_df, by = "time") %>%
    na.omit()
}

load_transmission_lines <- function() {
  if (file.exists(transmission_shp)) {
    tx <- st_read(transmission_shp, quiet = TRUE)
  } else {
    wfs_url <- paste0(
      "https://services.ga.gov.au/gis/services/National_Electricity_Infrastructure/",
      "MapServer/WFSServer?",
      "request=GetFeature&service=WFS&version=1.1.0&",
      "outputFormat=GML3&",
      "typeName=National_Electricity_Infrastructure:Electricity_Transmission_Lines"
    )

    tx <- st_read(wfs_url, quiet = TRUE)
    st_write(tx, transmission_shp, delete_layer = TRUE, quiet = TRUE)
  }

  tx %>%
    st_transform(4326) %>%
    #mutate(CAPACITYKV = suppressWarnings(as.numeric(CAPACITYKV))) %>%
    #filter(CAPACITYKV > 200)
    mutate(CAPACIT = suppressWarnings(as.numeric(CAPACIT))) %>%
    filter(CAPACIT > 200)
}

scatterplot_region_events <- function(d, region, t90, show_legend = TRUE) {
  d <- d %>%
    mutate(
      event_hour = if_else(is.na(event_hour), "No-Event hour", event_hour),
      event_day = if_else(is.na(event_day), "No-Event day", event_day),
      event_hour = factor(event_hour, levels = event_hour_levels),
      event_day = factor(event_day, levels = event_day_levels),
      x = pmin(x, 1)
    )

  p <- ggplot(d, aes(x = x, y = y)) +
    geom_point(
      aes(shape = event_hour, color = event_day, alpha = event_day),
      size = 3
    ) +
    geom_hline(yintercept = t90, color = "black", linetype = "dashed", linewidth = 1) +
    geom_vline(xintercept = 0.5, color = "black", linetype = "dashed", linewidth = 1) +
    scale_shape_manual(
      values = c(
        "Hot-Cloudy hour" = 17,
        "Hot-Sunny hour" = 4,
        "No-Event hour" = 1
      ),
      drop = FALSE,
      limits = event_hour_levels
    ) +
    scale_color_manual(
      values = c(
        "Hot-Cloudy day" = "#7f0000",
        "Hot-Sunny day" = "orange",
        "No-Event day" = "lightgrey"
      ),
      drop = FALSE,
      limits = event_day_levels
    ) +
    scale_alpha_manual(
      values = c(
        "Hot-Cloudy day" = 0.8,
        "Hot-Sunny day" = 0.8,
        "No-Event day" = 0.1
      ),
      drop = FALSE,
      limits = event_day_levels
    ) +
    labs(
      x = "CSI",
      y = "Temperature (°C)",
      title = region,
      shape = NULL,
      color = NULL,
      alpha = NULL
    ) +
    theme_minimal(base_size = 14)

  if (!show_legend) {
    p <- p + guides(color = "none", shape = "none", alpha = "none") +
      theme(legend.position = "none")
  }

  p
}

# =============================================================================
# Input data
# =============================================================================
hc_hours <- read.csv(hc_hours_file) %>%
  mutate(event_hour = "Hot-Cloudy hour")

null_hours <- read.csv(null_hours_file) %>%
  mutate(event_hour = "Hot-Sunny hour")

events_hours_df <- bind_rows(hc_hours, null_hours) %>%
  filter(region %in% regions) %>%
  mutate(time = ymd_hms(time, tz = "Australia/Brisbane"))

hc_days <- read.csv(hc_days_file) %>%
  mutate(event_day = "Hot-Cloudy day")

null_days <- read.csv(null_days_file) %>%
  mutate(
    nhours = 7,
    event_day = "Hot-Sunny day"
  )

events_day_df <- bind_rows(hc_days, null_days) %>%
  filter(region %in% regions) %>%
  mutate(date = as.Date(time)) %>%
  select(-time)

indep_copula_df <- read.csv(copula_file)

# =============================================================================
# Figure 1: map + scatter plots
# =============================================================================
world_coordinates <- map_data("world")
aus <- world_coordinates %>% filter(region == "Australia")

gccsa <- st_read(gccsa_shp, quiet = TRUE) %>%
  st_transform(4326) %>%
  filter(GCC_CODE21 %in% c("1GSYD", "2GMEL", "3GBRI", "4GADE")) %>%
  mutate(
    GCC_CODE21_clean = str_remove(GCC_CODE21, "^[0-9]+"),
    GCC_CODE21_clean = factor(GCC_CODE21_clean, levels = regions)
  )

tx_high <- load_transmission_lines()

label_df <- tibble(
  label = c("GBRI", "GSYD", "GMEL", "GADE"),
  lon = c(149, 148, 145, 138.5),
  lat = c(-27.5, -32, -36, -33)
)

lon_breaks <- seq(110, 160, by = 10)
lat_breaks <- seq(-45, -7, by = 5)

gp_map <- ggplot() +
  geom_polygon(
    data = aus,
    aes(x = long, y = lat, group = group),
    fill = "white",
    color = "grey35",
    linewidth = 0.3
  ) +
  geom_sf(
    data = tx_high,
    inherit.aes = FALSE,
    color = transmission_col,
    linewidth = 0.35,
    alpha = 0.8
  ) +
  geom_sf(
    data = gccsa,
    aes(fill = GCC_CODE21_clean),
    inherit.aes = FALSE,
    color = "grey20",
    linewidth = 0.25
  ) +
  geom_text(
    data = label_df,
    aes(x = lon, y = lat, label = label),
    inherit.aes = FALSE,
    size = 4.5,
    fontface = "bold",
    color = "grey40"
  ) +
  scale_fill_manual(values = region_cols, drop = FALSE, name = NULL) +
  coord_sf(xlim = range(lon_breaks), ylim = c(-45, -7), expand = FALSE) +
  scale_x_continuous(breaks = lon_breaks) +
  scale_y_continuous(breaks = lat_breaks) +
  labs(x = NULL, y = NULL) +
  theme_minimal(base_size = 14) +
  theme(
    panel.grid = element_blank(),
    legend.position = "none"
  )

scatter_plots <- vector("list", length(regions))

for (i in seq_along(regions)) {
  region_i <- regions[i]
  t90_i <- indep_copula_df[indep_copula_df$region == region_i, "t90"]

  data_df <- load_cloud_temperature(region_i, keep_hours = TRUE) %>%
    mutate(region = region_i)

  merge_df <- merge(data_df, events_hours_df, by = c("time", "region"), all.x = TRUE)
  merge_df$date <- as.Date(merge_df$time)

  merge_hour_day_df <- merge(
    merge_df,
    events_day_df,
    by = c("date", "region"),
    all.x = TRUE
  )

  scatter_plots[[i]] <- scatterplot_region_events(
    d = merge_hour_day_df,
    region = region_i,
    t90 = t90_i,
    show_legend = i == 1
  )
}

combined_scatter <- wrap_plots(scatter_plots, nrow = 2, ncol = 2) +
  plot_layout(guides = "collect") &
  theme(legend.position = "right")

figure1 <- (gp_map | wrap_elements(combined_scatter)) +
  plot_layout(widths = c(0.8, 1.2)) +
  plot_annotation(tag_levels = list(c("a)", "b)"))) &
  theme(
    plot.tag.position = c(0.02, 0.98),
    plot.tag = element_text(size = 16, face = "bold")
  )

ggsave(
  filename = file.path(plot_dir, "Figure1.png"),
  plot = figure1,
  width = 38,
  height = 20,
  units = "cm",
  bg = "white"
)

# =============================================================================
# Shared hourly data for Figure 2
# =============================================================================
tmp_all_regions_df <- list()
csi_all_regions_df <- list()

for (region_i in regions) {
  data_df <- load_cloud_temperature(region_i, keep_hours = FALSE) %>%
    mutate(region = region_i)

  merge_df <- merge(data_df, events_hours_df, by = c("time", "region"), all.x = TRUE)
  merge_df$date <- as.Date(merge_df$time)

  merge_hour_day_df <- merge(
    merge_df,
    events_day_df,
    by = c("date", "region"),
    all.x = TRUE
  )

  tmp_all_regions_df[[region_i]] <- merge_hour_day_df[, c("region", "time", "y", "event_hour", "nhours", "event_day")]
  csi_all_regions_df[[region_i]] <- merge_hour_day_df[, c("region", "time", "x", "event_hour", "nhours", "event_day")]
}

tmp_all_regions_df <- bind_rows(tmp_all_regions_df) %>%
  mutate(
    event_hour = if_else(is.na(event_hour), "No-Event hour", event_hour),
    event_day = if_else(is.na(event_day), "No-Event day", event_day),
    event_hour = factor(event_hour, levels = event_hour_levels),
    event_day = factor(event_day, levels = event_day_levels),
    time = hour(time),
    region = factor(as.character(region), levels = regions)
  )

csi_all_regions_df <- bind_rows(csi_all_regions_df) %>%
  mutate(
    event_hour = if_else(is.na(event_hour), "No-Event hour", event_hour),
    event_day = if_else(is.na(event_day), "No-Event day", event_day),
    event_hour = factor(event_hour, levels = event_hour_levels),
    event_day = factor(event_day, levels = event_day_levels),
    time = hour(time),
    x = pmin(x, 1),
    region = factor(as.character(region), levels = regions)
  )

tmp_all_regions_solar_df <- tmp_all_regions_df %>%
  filter(time %in% solar_hours)

csi_all_regions_solar_df <- csi_all_regions_df %>%
  filter(time %in% solar_hours)

# =============================================================================
# Demand data for Figure 2 and Figure S7
# =============================================================================
demand_df <- read.csv(demand_file)
colnames(demand_df) <- c("time", "GSYD", "GMEL", "GBRI", "GADE", "GHOB")

demand_df <- demand_df %>%
  select(time, GBRI, GSYD, GMEL, GADE) %>%
  mutate(
    time = ymd_hms(time, tz = "UTC"),
    time = with_tz(time, tzone = "Australia/Brisbane")
  ) %>%
  filter(year(time) %in% years, month(time) %in% months)

demand_long <- demand_df %>%
  pivot_longer(
    cols = -time,
    names_to = "region",
    values_to = "demand"
  ) %>%
  mutate(region = factor(region, levels = regions))

events_hours_df2 <- events_hours_df %>%
  mutate(
    region = factor(region, levels = regions),
    time = floor_date(time, "hour"),
    event_hour = as.character(event_hour)
  )

demand_event_hour <- demand_long %>%
  filter(hour(time) %in% solar_hours) %>%
  mutate(time = floor_date(time, "hour")) %>%
  left_join(events_hours_df2, by = c("time", "region")) %>%
  mutate(
    hour = hour(time),
    event_hour = if_else(is.na(event_hour), "No-Event hour", event_hour),
    event_hour = factor(event_hour, levels = event_hour_levels)
  )

plot_df_hour <- demand_event_hour %>%
  mutate(hour = as.integer(hour))

# =============================================================================
# Figure 2: hourly temperature, CSI, and demand profiles
# =============================================================================
ggp_tmp_solarHours <- ggplot(
  tmp_all_regions_solar_df,
  aes(x = factor(time), y = y, fill = event_hour)
) +
  geom_boxplot(alpha = 0.7, outlier.colour = "grey") +
  scale_fill_manual(values = fill_vals, name = "Event hour") +
  theme_minimal() +
  facet_wrap(vars(region), scales = "free_y", nrow = 1, ncol = 4) +
  theme(
    axis.text.x = element_text(hjust = 1),
    panel.grid.minor = element_blank(),
    legend.position = "none"
  ) +
  labs(
    x = NULL,
    y = "Temperature (°C)",
    title = "a) Hourly temperature profile"
  )

ggp_csi_solarHours <- ggplot(
  csi_all_regions_solar_df,
  aes(x = factor(time), y = x, fill = event_hour)
) +
  geom_boxplot(alpha = 0.7, outlier.colour = "grey") +
  scale_fill_manual(values = fill_vals, name = "Event hour") +
  theme_minimal() +
  facet_wrap(vars(region), scales = "free_y", nrow = 1, ncol = 4) +
  theme(
    axis.text.x = element_text(hjust = 1),
    panel.grid.minor = element_blank(),
    legend.position = "none"
  ) +
  labs(
    x = NULL,
    y = "CSI",
    title = "b) Hourly CSI profile"
  )

ggp_demand_hour <- ggplot(
  plot_df_hour,
  aes(x = factor(hour), y = demand, fill = event_hour)
) +
  geom_boxplot(alpha = 0.7, outlier.colour = "grey") +
  facet_wrap(vars(region), scales = "free_y", nrow = 1, ncol = 4) +
  scale_fill_manual(values = fill_vals, name = "Event hour") +
  theme_minimal(base_size = 12) +
  theme(
    panel.grid.minor = element_blank(),
    legend.position = "none"
  ) +
  labs(
    x = NULL,
    y = "Demand (MW)",
    title = "c) Hourly demand profile"
  )

legend_plot <- ggplot(
  data.frame(
    event_hour = factor(event_hour_levels, levels = event_hour_levels),
    x = 1,
    y = 1
  ),
  aes(x, y, fill = event_hour)
) +
  geom_point(shape = 22, size = 0, alpha = 0) +
  scale_fill_manual(values = fill_vals, name = NULL) +
  guides(fill = guide_legend(
    override.aes = list(
      shape = 22,
      size = 6,
      alpha = 1,
      colour = NA
    )
  )) +
  theme_void() +
  theme(
    legend.position = "bottom",
    plot.background = element_blank(),
    panel.background = element_blank(),
    plot.margin = margin(0, 0, 0, 0)
  )

one_legend <- wrap_plots(legend_plot) +
  plot_layout(guides = "collect") &
  theme(legend.position = "bottom")

figure2 <- ((ggp_tmp_solarHours / ggp_csi_solarHours / ggp_demand_hour) / one_legend) +
  plot_layout(heights = c(1, 1, 1, 0.08)) &
  theme(
    plot.background = element_rect(fill = "white", colour = NA),
    legend.background = element_blank(),
    legend.box.background = element_blank()
  )

ggsave(
  filename = file.path(plot_dir, "Figure2.png"),
  plot = figure2,
  width = 40,
  height = 20,
  units = "cm",
  bg = "white"
)

# =============================================================================
# Figure S7: hourly demand by day type
# =============================================================================
events_day_df2 <- events_day_df %>%
  mutate(region = factor(region, levels = regions))

demand_event_day <- demand_long %>%
  mutate(date = as.Date(time)) %>%
  left_join(events_day_df2, by = c("date", "region")) %>%
  mutate(
    hour = hour(time),
    event_day = if_else(is.na(event_day), "No-Event day", event_day),
    event_day = factor(event_day, levels = event_day_levels)
  )

plot_df_day <- demand_event_day %>%
  mutate(hour = as.integer(hour))

figureS7 <- ggplot(plot_df_day, aes(x = factor(hour), y = demand, fill = event_day)) +
  geom_boxplot(alpha = 0.7, outlier.colour = "grey") +
  facet_wrap(~region, scales = "free_y") +
  scale_fill_manual(values = fill_day_vals, name = NULL) +
  labs(x = "Hour", y = "Demand (MW)") +
  theme_minimal(base_size = 12) +
  theme(
    legend.position = "bottom",
    panel.grid.minor = element_blank(),
    legend.title = element_blank()
  )

ggsave(
  filename = file.path(plot_dir, "FigureS7.png"),
  plot = figureS7,
  width = 40,
  height = 18,
  units = "cm",
  bg = "white"
)

print(figure1)
print(figure2)
print(figureS7)
