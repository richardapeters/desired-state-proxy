# Desired State Proxy

Desired state proxy (digital twin) for Home Assistant.

`Desired State Proxy` is a Home Assistant custom integration (helper) that creates a **proxy
entity** for an existing `switch` or `light`. The proxy represents the **desired** state, while
the original entity keeps representing the **actual** state of the physical device.

When the physical device is unreachable — a Zigbee bulb that lost mains power, a Wi-Fi plug that
is rebooting, a battery device that is asleep — the proxy stays available, remembers what you
asked for, and applies it automatically as soon as the device comes back.

## Why?

Home Assistant entities go `unavailable` when their device disappears. Automations, scripts and
dashboards that target such an entity silently do nothing, and the command is lost forever. With
a desired state proxy you get:

- **Always available control.** The proxy never becomes `unavailable`, so automations always work.
- **Automatic reconciliation.** When the source device returns, the proxy pushes the last desired
  state to it.
- **Digital twin semantics.** `desired_state` (proxy) vs `actual_state` (source) is visible at a
  glance, together with a `pending` flag.
- **Survives restarts.** The desired state is persisted in the config entry options.

## Installation

### HACS (custom repository until default-store inclusion)

1. In HACS, choose *Integrations* → ⋮ → *Custom repositories*.
2. Add `https://github.com/richardapeters/desired-state-proxy` as an *Integration*.
3. Install **Desired State Proxy** and restart Home Assistant.

To publish this repository in the default HACS store, make sure the HACS validation and Hassfest
workflows are passing, then create a GitHub release and submit the repository to
[`hacs/default`](https://github.com/hacs/default).

### Manual

1. Copy the `custom_components/desired_state` directory into your Home Assistant
   `config/custom_components` directory.
2. Restart Home Assistant.

## Configuration

Add the helper via the UI: **Settings → Devices & services → Helpers → Create helper →
Desired State Proxy**.

| Option | Description |
| --- | --- |
| **Source entity** | The `switch` or `light` entity whose actual state is tracked. |
| **Proxy type** | `Automatic`, `Switch` or `Light`. Automatic creates a light proxy for a light source and a switch proxy for a switch source. |
| **Proxy name** | Name of the proxy entity. Leave empty to derive it from the source entity (`<Friendly name> Desired`). |
| **Hide the source entity** | Hides the source entity in the UI so only the proxy is shown. The source entity is unhidden again when the proxy is removed. |

Rules enforced by the config flow:

- An entity can only be proxied once.
- A proxy entity of this integration cannot be used as a source (no proxy chains).
- A **switch** proxy can only proxy a `switch` source.
- A **light** proxy can proxy either a `light` or a `switch` source. Proxying a switch as a light
  only exposes on/off (color mode `onoff`).

The name and the *hide source* option can be changed afterwards through the *Configure* button of
the helper.

## Behaviour

### Semantics

| | Proxy entity | Source entity |
| --- | --- | --- |
| `state` | desired state | actual device state |
| `available` | always `true` | depends on the device |

1. Turning the proxy on/off updates the **desired** state immediately, and the proxy state changes
   right away — regardless of the source being reachable.
2. If the source is available and its state differs from the desired state, the proxy calls
   `switch.turn_on` / `switch.turn_off` / `light.turn_on` / `light.turn_off` on the **source**
   entity (never on itself, so no loops are possible).
3. If the source is unavailable, nothing is sent. The proxy sets `pending: true` and waits.
4. As soon as the source becomes available again, the desired state is pushed to it.
5. If the source does not follow within a few seconds, the command is retried a limited number of
   times. Retries reset when the source becomes available again or when a new desired state is set.
6. No command is sent when the source already matches the desired state.

### Light parameters

For a light proxy on a light source, the brightness, color temperature and RGB color are part of
the desired state and are remembered while the source is offline. When the light returns, the
remembered parameters are applied together with the on command. The proxy mirrors the
`supported_color_modes` and `supported_features` of the source light.

### Attributes

Every proxy entity exposes:

| Attribute | Description |
| --- | --- |
| `source_entity` | Entity id of the proxied entity. |
| `desired_state` | `on` or `off` — what you asked for. |
| `actual_state` | Raw state of the source entity (`on`, `off`, `unavailable`, `unknown`). |
| `pending` | `true` when the source does not (yet) match the desired state. |
| `desired_brightness` | Remembered brightness (light proxies). |
| `desired_color_temp` | Remembered color temperature in Kelvin (light proxies). |
| `desired_rgb_color` | Remembered RGB color (light proxies). |

### Persistence

The desired state is stored in the **options** of the config entry (`desired_on`,
`desired_brightness`, `desired_color_temp`, `desired_rgb_color`, `desired_hs_color`), so it
survives Home Assistant restarts and integration reloads without creating new entities.

## Example

```yaml
automation:
  - alias: "Turn on the shed light at sunset"
    trigger:
      - platform: sun
        event: sunset
    action:
      # Works even when the shed light has no power right now.
      - service: light.turn_on
        target:
          entity_id: light.shed_desired
        data:
          brightness: 180
```

When the shed light is powered up again — hours later — it is turned on at brightness 180
automatically.

Showing the difference between desired and actual state on a dashboard:

```yaml
type: entities
entities:
  - entity: light.shed_desired
    name: Desired
  - type: attribute
    entity: light.shed_desired
    attribute: actual_state
    name: Actual
  - type: attribute
    entity: light.shed_desired
    attribute: pending
    name: Pending
```

## Diagnostics

Download diagnostics from the integration entry to inspect the configuration, the desired state,
the actual state of the source and whether both are in sync.

## Repository layout

```
custom_components/desired_state/
├── __init__.py        # setup/unload/remove of config entries
├── brand/
│   └── icon.png       # HACS / Home Assistant brand asset
├── config_flow.py     # UI configuration and validation
├── const.py           # constants
├── coordinator.py     # desired state storage, reconciliation and retries
├── diagnostics.py     # config entry diagnostics
├── entity.py          # shared proxy entity base class
├── light.py           # light proxy platform
├── switch.py          # switch proxy platform
├── manifest.json
├── strings.json
├── translations/en.json
└── tests/             # pytest suite
```

## Development

```bash
pip install homeassistant==2025.1.4 pytest==8.3.4 pytest-homeassistant-custom-component==0.13.205 pytest-asyncio==0.24.0
python -m pytest custom_components/desired_state/tests/ -q
```

Repository validation for HACS publishing is also configured through:

- `.github/workflows/validate.yml` for `hacs/action`
- `.github/workflows/hassfest.yml` for `home-assistant/actions/hassfest`
- `.github/workflows/integration-tests.yml` for the pytest integration test suite

The test suite covers the switch proxy, the light proxy (from both light and switch sources),
reconciliation, retries, persistence, diagnostics and the config flow.

## License

MIT
