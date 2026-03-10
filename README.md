# UVI HKVO Consumption Tracker

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/)

Home Assistant custom integration for UVI tenant portals.

It logs into the tenant portal, fetches consumption data, and publishes dynamic sensor entities for heating, warm water, cold water, monthly comparisons, and meter-level details.

## Features

- Config Flow setup in Home Assistant UI
- CSRF + cookie-based portal login
- Billing-period-first fetch strategy with adaptive fallback for sparse readout schedules
- Dynamic group discovery (not limited to fixed `h1/k1/w1` assumptions)
- Multiple meter support per group
- Combo meter deduplication — meters appearing in multiple endpoints (e.g. warm + cold water) are published only once
- Per-meter sensors: period consumption, absolute meter reading (`total_increasing`), and energy (kWh, where available)
- Aggregated readout total sensors per group (e.g. `heating_meters_h1_readout_total`) — ready for the HA Energy Dashboard
- Aggregated energy total sensors in kWh (e.g. `heating_meters_h1_energy_total`) — `total_increasing` + `device_class: energy`, directly usable in the Energy Dashboard Gas section
- Area sensors from estate-unit metadata (`heated_area`, `warm_water_area`, `area`)
- Billing-period consumption from the summary endpoint
- Three levels of reference data:
  - **Your own previous year** (same months year-over-year)
  - **Building average** (all units in your property for the same period)
  - **All-buildings benchmark** (portfolio-wide reference across all properties)
- Comparison sensors:
  - Month over month (latest complete month vs prior month)
  - Year over year — same period (e.g. Jan-Feb 2026 vs Jan-Feb 2025)
  - Same month last year (e.g. Feb 2026 vs Feb 2025)
  - vs building average (period) / vs all-buildings benchmark
  - Climate-corrected comparison year totals (where available from the API)
- Incomplete-month protection: comparisons automatically skip partial months so you never compare an incomplete month against a full one
- Monthly-comparison totals/deltas with full month series in attributes (instead of one entity per month)
- Historical monthly-comparison backfill (best effort)
- Rich `description` attribute on every sensor explaining what it means
- `period_label` attributes on time-dependent sensors, derived from the actual API query window (e.g. "Jan-Feb 2026", "Feb 2026 vs Feb 2025")
- `window_from` / `window_to` attributes on consumption and summary sensors showing the exact date range queried
- Configurable update interval (default: once per day)
- Core sensors enabled by default; advanced/diagnostic sensors disabled by default (can be enabled in Entity Registry)

## Installation (HACS)

1. Open HACS → Integrations.
2. Click the three-dot menu (top right) → **Custom repositories**.
3. Enter `https://github.com/tobiasv1337/home-assistant-uvi-hkvo-consumption-tracker` and select type **Integration**. Click **Add**.
4. Search for `UVI HKVO Consumption Tracker` and install it.
5. Restart Home Assistant.
6. Go to **Settings → Devices & Services → Add Integration** and search for `UVI HKVO`.

## Configuration

Required:

- `Base URL` (example: `https://uvi.wmd-altmark.de`)
- `Email`
- `Password`

Optional:

- `Update interval (minutes)`

Default is `1440` minutes (once daily).

## API Endpoints Used

- `/tenant_portal_users/sign_in`
- `/api/user`
- `/api/estate-units`
- `/api/summary`
- `/api/heating`
- `/api/warm-water`
- `/api/cold-water`
- `/api/monthly-comparison`

## Data Strategy

Each consumption endpoint (`heating`, `warm-water`, `cold-water`) first tries the **full billing-period window** (calendar year: Jan 1 – today). If the API returns no data for that range, the integration falls back to an adaptive probing strategy with increasingly wider windows (`1, 2, 3, 7, 14, 30` days, then per-month). Each endpoint is fetched independently, so one can use a wider window without reducing detail for the others.

Summary endpoints also use the billing-period window first, with month-by-month fallback.

The selected query window is attached as sensor attributes (`window_from`, `window_to`, `window_label`, `window_selection_reason`) so you can see exactly which API range produced the current values.

On initial setup, monthly-comparison history is backfilled year-by-year (best effort).

## Sensor Overview

Every sensor has a `description` attribute explaining what it represents and a `period_label` where applicable (e.g. "Feb 2026", "Jan-Feb 2026 vs Jan-Feb 2025"). Consumption and summary sensors also carry `window_from` / `window_to` attributes showing the exact date range queried from the API.

### Enabled by default (core sensors)

| Category | Example entity key | Example name | Description |
|---|---|---|---|
| **Billing period** | `summary_current_h1_consumption` | Heating Billing Period | Total consumption from billing period start |
| **Billing period energy** | `summary_current_w1_normalized_kwh` | Warm Water Billing Period Energy | Normalized kWh for the billing period |
| **Latest month** | `heating_current_month_h1_consumption` | Heating Latest Month | Latest complete month from the endpoint |
| **Latest month energy** | `heating_current_month_h1_normalized_kwh` | Heating Latest Month Energy | Latest month kWh (where available) |
| **Per-meter consumption** | `meter_heat_1001_h1_consumption` | HEAT-1001 Consumption | Period consumption per physical meter |
| **Per-meter reading** | `meter_heat_1001_h1_readout_total` | HEAT-1001 Meter Reading | Absolute cumulative meter reading (`total_increasing`) |
| **Per-meter energy** | `meter_heat_1001_h1_normalized_kwh` | HEAT-1001 Energy | Normalized kWh per meter |
| **Aggregated reading** | `heating_meters_h1_readout_total` | Heating Total Meter Reading | Sum of all meter readings in the group (`total_increasing`) |
| **Aggregated energy** | `heating_meters_h1_energy_total` | Heating Total Energy | Sum of all kWh estimates (`total_increasing`, Energy Dashboard) |
| **vs Building** | `summary_current_vs_building_average_h1_delta_percent` | Heating vs Building (Period) | % difference to building average (same billing period) |
| **vs All-Buildings** | `summary_current_vs_average_tenant_h1_delta_percent` | Heating vs All-Buildings Benchmark | % difference to portfolio-wide benchmark |
| **Month over month** | `comparison_h1_current_vs_previous_month_delta_percent` | Heating Month over Month | Latest month vs prior month (%) |
| **Same month last year** | `comparison_h1_current_month_delta_percent` | Heating vs Same Month Last Year | Same month year-over-year (%) |
| **Year over year** | `comparison_h1_delta_percent_total` | Heating Year over Year (Same Period) | Same months cumulative comparison (%) |
| **Same month last year (value)** | `comparison_h1_current_month_comparison` | Heating Same Month Last Year | Last year's value for the same month |
| **Area** | `estate_unit_heated_area` | Heated Area | Estate unit area metadata |

### Disabled by default (diagnostic sensors)

These can be enabled manually in the Entity Registry:

- Year totals: `Heating This Year to Date`, `Heating Last Year Same Period`, `Heating Last Year Same Period Climate Adj.`
- Building averages: `Heating Building Avg (Period)`, `Heating All-Buildings Benchmark`, `Heating Building Avg (Latest Month)`
- Absolute deltas: `Heating vs Building (Period) Diff`, `Heating Month over Month Diff`
- Estate unit totals: `Heating Unit Total (Period)` (for multi-unit accounts)
- Historical data: `Heating Historical Data Points`
- Account info: `Estate Units Count`

## Energy Dashboard

### Water (cold + warm)

Water meter `readout_total` sensors use `state_class: total_increasing` with `device_class: water` and unit `m³`. These can be added **directly** to the HA Energy Dashboard under **Water consumption**:

- Individual meters: `meter_cw_3001_k1_readout_total`, `meter_ww_2001_w1_readout_total`
- Aggregated totals: `cold_water_meters_k1_readout_total`, `warm_water_meters_w1_readout_total`

### Heating

The raw heating meters report in **HKV** (Heizkostenverteiler / heat cost allocator units). HKV values cannot be used directly in the Energy Dashboard's Gas section, which requires kWh.

However, the API provides an **estimated kWh conversion** (`normalized_kwh_consumption`) for each HKV meter. The integration creates **per-meter** kWh sensors as well as an **aggregated total**:

| Sensor | Example | Unit | `state_class` | Use case |
|---|---|---|---|---|
| `meter_heat_XXXX_h1_normalized_kwh` | `meter_heat_1001_h1_normalized_kwh` | kWh | `total_increasing` | Per-room energy in Energy Dashboard |
| `heating_meters_h1_energy_total` | — | kWh | `total_increasing` | Total heating energy in Energy Dashboard |

All these sensors have `device_class: energy` and can be added **directly** to the HA Energy Dashboard under **Gas consumption** (select the kWh unit variant). Using the per-meter sensors lets you compare which room consumes the most energy.

> The HKV readout totals (`heating_meters_h1_readout_total`, `meter_heat_XXXX_h1_readout_total`) remain available for dashboards and automations but are **not** compatible with the Energy Dashboard.

### Warm Water Energy

Warm water meters also expose per-meter and aggregated kWh sensors derived from the API's `normalized_kwh_consumption`:

| Sensor | Example | Unit | `state_class` | Use case |
|---|---|---|---|---|
| `meter_ww_XXXX_w1_normalized_kwh` | `meter_ww_2001_w1_normalized_kwh` | kWh | `total_increasing` | Per-meter energy in Energy Dashboard |
| `warm_water_meters_w1_energy_total` | — | kWh | `total_increasing` | Total warm water energy in Energy Dashboard |

These can be used in the Energy Dashboard under **Gas consumption** to track the energy component of warm water separately from the volumetric `m³` water sensors.

### Month-over-Month Comparisons

Comparisons automatically use only **complete months**. If the current calendar month is still in progress (or marked `incomplete` by the API), the integration compares the last full month with the month before it. This prevents misleading partial-month comparisons.

## Development and Tests

Recommended tool: `uv`.

### Setup

```bash
uv sync --extra dev
cp .env.template .env
```

### Offline Tests (no real portal access)

```bash
uv run pytest -m offline
```

### Online Tests (real portal access)

```bash
uv run pytest -m online -s
```

### Verbose Test Output

Use `--uvi-verbose`.

```bash
uv run pytest -m offline -s --uvi-verbose
uv run pytest -m online -s --uvi-verbose
```

Verbose mode includes detailed endpoint mapping and full entity publication reports (keys, values, units, attributes).

## License

Proprietary / All rights reserved (for now).

## Disclaimer

Unofficial integration. Not affiliated with metering providers. API contracts may change.
