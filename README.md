# SniffWorks

SniffWorks is a collection of protocol sniffer applications built on a shared framework. Each app focuses on a specific protocol while reusing common foundations for capturing, inspecting, and working with data.

The project starts with an I²C sniffer. That existing I²C project will be brought into this repository and serve as the first app built on the shared framework. SniffWorks is intended to grow to support additional protocols, including CAN, USB, SPI, and UART.

## Project Direction

- Build each protocol sniffer as a separate app.
- Share a common framework across apps instead of reimplementing foundational functionality for each protocol.
- Keep protocol-specific capture and decoding behavior in its corresponding app.
- Use the I²C sniffer as the starting point for shaping the framework and app structure.

## Planned Sniffers

| Protocol | Status |
| --- | --- |
| I²C | Initial app; project to be migrated into this repository |
| CAN | Planned |
| USB | Planned |
| SPI | Planned |
| UART | Planned |

## Roadmap

1. Bring the existing I²C sniffer into the repository.
2. Identify the reusable foundations it can provide to other sniffer apps.
3. Establish the shared framework and keep the I²C app working on it.
4. Add further protocol-specific apps as the framework evolves.