library(lubridate)
library(ggplot2)
library(tidyverse)
library(dplyr)
library(scales)

# =============================================================================
# Directories and files
# =============================================================================
base_dir <- "hot-cloudy"

events_dir <- file.path(base_dir, "data")
plot_dir <- file.path(base_dir, "figs")

hc_days_file <- file.path(events_dir, "event_dates_csi0p5_thourly90_counts.csv")
null_days_file <- file.path(events_dir, "null_event_dates_csi0p5_thourly90_nhours7.csv")

if (!dir.exists(plot_dir)) dir.create(plot_dir, recursive = TRUE)

# =============================================================================
# Settings
# =============================================================================
regions <- c("GBRI", "GSYD", "GMEL", "GADE")
months_keep <- c(1, 2, 3, 4, 11, 12)
gap_days <- 1

event_levels <- c("Hot-Cloudy day", "Hot-Sunny day")
region_cols <- c(
  "GBRI" = "#EB9DA2",
  "GSYD" = "#F0B884",
  "GMEL" = "#BBEBB5",
  "GADE" = "#ACBBE8"
)

region_y <- c(
  "GBRI" = 0.55,
  "GSYD" = 0.40,
  "GMEL" = 0.25,
  "GADE" = 0.10
)

figure_names <- c(
  "GBRI" = "FigureS1.png",
  "GSYD" = "FigureS2.png",
  "GMEL" = "FigureS3.png",
  "GADE" = "FigureS4.png"
)

# =============================================================================
# Input data
# =============================================================================
hc_days <- read.csv(hc_days_file) %>%
  mutate(event = "Hot-Cloudy day")

null_days <- read.csv(null_days_file) %>%
  mutate(
    nhours = 7,
    event = "Hot-Sunny day"
  )

events_df <- bind_rows(hc_days, null_days) %>%
  filter(region %in% regions) %>%
  mutate(
    event = factor(event, levels = event_levels),
    time = as.Date(time)
  )

# =============================================================================
# Helpers
# =============================================================================
plot_region_cut_calendar <- function(data, region_code, gap_days = 1) {
  ev0 <- data %>%
    mutate(
      year = lubridate::year(time),
      month = lubridate::month(time)
    ) %>%
    filter(region == region_code, month %in% months_keep)

  if (nrow(ev0) == 0) {
    return(ggplot() + labs(title = region_code, subtitle = "No events"))
  }

  ev <- ev0 %>%
    group_by(year) %>%
    mutate(
      jan_start = as.Date(sprintf("%d-01-01", year)),
      apr_end = as.Date(sprintf("%d-04-30", year)),
      nov_start = as.Date(sprintf("%d-11-01", year)),
      len_JFMA = as.integer(apr_end - jan_start) + 1,
      len_ND_cal = as.integer(as.Date(sprintf("%d-12-31", year)) - nov_start) + 1,
      has_ND = any(month %in% c(11, 12)),
      display_x = dplyr::case_when(
        month %in% 1:4 ~ as.integer(time - jan_start) + 1,
        month %in% c(11, 12) ~ len_JFMA + if_else(has_ND, gap_days, 0L) + as.integer(time - nov_start) + 1
      )
    ) %>%
    ungroup()

  limits <- ev %>%
    distinct(year, len_JFMA, len_ND_cal, has_ND) %>%
    mutate(
      x_min = 1L,
      x_max = len_JFMA + if_else(has_ND, gap_days + len_ND_cal, 0L)
    )

  baselines <- dplyr::bind_rows(
    limits %>% transmute(year, x1 = 1L, x2 = len_JFMA),
    limits %>%
      filter(has_ND) %>%
      transmute(
        year,
        x1 = len_JFMA + gap_days,
        x2 = len_JFMA + gap_days + len_ND_cal
      )
  )

  ticks <- ev %>%
    arrange(year, display_x, event) %>%
    distinct(year, display_x, time)

  limits_pts <- limits %>%
    select(year, x_min, x_max) %>%
    tidyr::pivot_longer(c(x_min, x_max), names_to = "which", values_to = "x") %>%
    mutate(y = 0)

  hot_labels <- ev %>%
    filter(event == "Hot-Cloudy day") %>%
    group_by(year, display_x) %>%
    summarise(nhours = max(nhours, na.rm = TRUE), .groups = "drop") %>%
    mutate(y = 0)

  ggplot() +
    geom_blank(data = limits_pts, aes(x = x, y = y)) +
    geom_segment(
      data = baselines,
      aes(x = x1, xend = x2, y = 0, yend = 0),
      linewidth = 0.6,
      colour = "grey55"
    ) +
    geom_linerange(
      data = ev,
      aes(x = display_x, ymin = -0.5, ymax = 0.5, colour = event),
      linewidth = 1.6
    ) +
    geom_text(
      data = ticks,
      aes(x = display_x, y = -0.55, label = format(time, "%d %b")),
      angle = 90,
      vjust = 0.5,
      hjust = 1,
      size = 2.7
    ) +
    geom_text(
      data = hot_labels,
      aes(x = display_x, y = y, label = nhours),
      colour = "cyan",
      size = 4,
      fontface = "bold"
    ) +
    facet_wrap(~ year, ncol = 1, scales = "free_x") +
    scale_colour_manual(
      values = c(
        "Hot-Cloudy day" = "#7f0000",
        "Hot-Sunny day" = "orange"
      ),
      breaks = event_levels,
      name = NULL
    ) +
    scale_x_continuous(expand = c(0, 0)) +
    scale_y_continuous(NULL, breaks = NULL, limits = c(-0.65, 0.7)) +
    coord_cartesian(clip = "off") +
    labs(
      title = region_code,
      x = NULL,
      subtitle = "Hot-Cloudy days and Hot-Sunny days"
    ) +
    guides(colour = guide_legend(override.aes = list(size = 3))) +
    theme_minimal(base_size = 10) +
    theme(
      panel.grid = element_blank(),
      strip.text = element_text(face = "bold"),
      axis.text.x = element_blank(),
      axis.ticks.x = element_blank(),
      legend.position = "bottom",
      legend.title = element_blank(),
      plot.margin = margin(5.5, 30, 5.5, 5.5)
    )
}

plot_all_regions_hot_cloudy <- function(data, gap_days = 1) {
  ev0 <- data %>%
    mutate(
      year = lubridate::year(time),
      month = lubridate::month(time)
    ) %>%
    filter(region %in% regions, month %in% months_keep, event == "Hot-Cloudy day")

  ev <- ev0 %>%
    group_by(year) %>%
    mutate(
      jan_start = as.Date(sprintf("%d-01-01", year)),
      apr_end = as.Date(sprintf("%d-04-30", year)),
      nov_start = as.Date(sprintf("%d-11-01", year)),
      len_JFMA = as.integer(apr_end - jan_start) + 1,
      len_ND_cal = as.integer(as.Date(sprintf("%d-12-31", year)) - nov_start) + 1,
      has_ND = any(month %in% c(11, 12)),
      display_x = dplyr::case_when(
        month %in% 1:4 ~ as.integer(time - jan_start) + 1,
        month %in% c(11, 12) ~ len_JFMA + if_else(has_ND, gap_days, 0L) + as.integer(time - nov_start) + 1
      )
    ) %>%
    ungroup() %>%
    mutate(y_region = unname(region_y[as.character(region)]))

  limits <- ev %>%
    distinct(year, len_JFMA, len_ND_cal, has_ND) %>%
    mutate(
      x_min = 1L,
      x_max = len_JFMA + if_else(has_ND, gap_days + len_ND_cal, 0L)
    )

  baselines <- dplyr::bind_rows(
    limits %>% transmute(year, x1 = 1L, x2 = len_JFMA),
    limits %>%
      filter(has_ND) %>%
      transmute(
        year,
        x1 = len_JFMA + gap_days,
        x2 = len_JFMA + gap_days + len_ND_cal
      )
  )

  ticks <- ev %>%
    arrange(year, display_x, region, event) %>%
    distinct(year, display_x, time)

  limits_pts <- limits %>%
    select(year, x_min, x_max) %>%
    tidyr::pivot_longer(c(x_min, x_max), names_to = "which", values_to = "x") %>%
    mutate(y = 0)

  ggplot() +
    geom_blank(data = limits_pts, aes(x = x, y = y)) +
    geom_segment(
      data = baselines,
      aes(x = x1, xend = x2, y = 0, yend = 0),
      linewidth = 0.6,
      colour = "grey55"
    ) +
    geom_point(
      data = ev,
      aes(x = display_x, y = y_region, colour = region),
      size = 2.2
    ) +
    geom_text(
      data = ticks,
      aes(x = display_x, y = -0.20, label = format(time, "%d %b")),
      angle = 90,
      vjust = 0.5,
      hjust = 1,
      size = 2.7
    ) +
    facet_wrap(~ year, ncol = 1, scales = "free_x") +
    scale_colour_manual(values = region_cols, breaks = names(region_cols), name = NULL) +
    scale_x_continuous(expand = c(0, 0)) +
    scale_y_continuous(NULL, breaks = NULL, limits = c(-0.30, 0.75)) +
    coord_cartesian(clip = "off") +
    labs(
      title = "Hot-Cloudy events",
      x = NULL
    ) +
    guides(colour = guide_legend(override.aes = list(size = 3))) +
    theme_minimal(base_size = 12) +
    theme(
      panel.grid.major.x = element_blank(),
      panel.grid.minor = element_blank(),
      strip.text = element_text(face = "bold"),
      axis.text.x = element_blank(),
      axis.ticks.x = element_blank(),
      legend.position = "bottom",
      plot.title = element_text(size = 18, face = "bold", hjust = 0.5),
      plot.margin = margin(5.5, 30, 5.5, 5.5)
    )
}

# =============================================================================
# Figure S1 to Figure S4: single-region day timelines
# =============================================================================
for (region_code in regions) {
  p_region <- plot_region_cut_calendar(events_df, region_code, gap_days = gap_days)

  ggsave(
    filename = file.path(plot_dir, figure_names[[region_code]]),
    plot = p_region,
    width = 40,
    height = 21,
    units = "cm",
    bg = "white"
  )
}

# =============================================================================
# Figure S5: Hot-Cloudy events for all four regions
# =============================================================================
figureS5 <- plot_all_regions_hot_cloudy(events_df, gap_days = gap_days)

ggsave(
  filename = file.path(plot_dir, "FigureS5.png"),
  plot = figureS5,
  width = 40,
  height = 21,
  units = "cm",
  bg = "white"
)

# =============================================================================
# Figure S6: distribution of Hot-Cloudy event duration
# =============================================================================
plot_df <- events_df %>%
  filter(event == "Hot-Cloudy day") %>%
  mutate(
    nhours = as.integer(nhours),
    duration = factor(nhours, levels = 1:7, labels = as.character(1:7))
  ) %>%
  filter(!is.na(duration))

plot_summ <- plot_df %>%
  count(region, duration, name = "n") %>%
  group_by(region) %>%
  mutate(p = n / sum(n)) %>%
  ungroup()

figureS6 <- ggplot(plot_summ, aes(x = duration, y = p)) +
  geom_col(fill = "#7f0000", width = 0.9) +
  geom_text(aes(label = n), vjust = -0.3, size = 3) +
  facet_wrap(~ region) +
  scale_y_continuous(
    labels = scales::percent_format(accuracy = 1),
    expand = expansion(mult = c(0, 0.12))
  ) +
  labs(
    x = "Duration (hours)",
    y = "Relative frequency",
    title = "Duration of Hot-Cloudy events on Hot-Cloudy days"
  ) +
  theme_minimal() +
  theme(
    panel.grid.major = element_line(),
    panel.grid.minor = element_line(),
    panel.grid.minor.x = element_blank()
  )

ggsave(
  filename = file.path(plot_dir, "FigureS6.png"),
  plot = figureS6,
  width = 15,
  height = 13,
  units = "cm",
  bg = "white"
)

# =============================================================================
# Sequencing tables: compute and display only
# =============================================================================
sequencing_df <- plot_df %>%
  mutate(time = as.Date(time, format = "%Y-%m-%d")) %>%
  arrange(desc(time)) %>%
  mutate(
    region_prev = lead(region),
    time_prev = lead(time),
    duration_prev = lead(duration),
    days_since_prev_event = as.integer(time - time_prev)
  )

sequencing_0_3_df <- sequencing_df %>%
  filter(days_since_prev_event <= 3)

sequencing_0_3_reshape_p1 <- sequencing_0_3_df[, c("time", "region", "days_since_prev_event", "region_prev")]
colnames(sequencing_0_3_reshape_p1) <- c("time", "region", "days_lag", "link_with")

sequencing_0_3_reshape_p2 <- sequencing_0_3_df[, c("time_prev", "region_prev", "days_since_prev_event", "region")]
colnames(sequencing_0_3_reshape_p2) <- c("time", "region", "days_lag", "link_with")

sequencing_0_3_reshape_nodup <- bind_rows(
  sequencing_0_3_reshape_p1,
  sequencing_0_3_reshape_p2
) %>%
  distinct(region, time, .keep_all = TRUE)

print(sequencing_df)
print(sequencing_0_3_reshape_nodup)

print(figureS5)
print(figureS6)
