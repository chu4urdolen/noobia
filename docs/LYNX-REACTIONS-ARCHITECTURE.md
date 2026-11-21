# Lynx Scripted Reaction Layer Architecture

## Overview
A fast, programmable reflex and reaction layer positioned between Aigel (perception interpretation / instinct) and Lynx (conscious agent).

```
Sensors (Camera, Touch, Light, Proximity, Hearing, WiFi, Power, Network)
                          │
                   noobia-sense lines
                          │
                    [Ranker & DB]
             (Strips IGNORE / null lines)
                          │
               Unexplained Perceptions
                          │
                    Aigel (Nexus)
                          │
              Perception Delivery / Alerts
                          │
          ┌───────────────▼──────────────┐
          │  Lynx Scripted Reaction Layer │  <── Programmed & modified by Lynx herself
          │    (Instant reflexes & state) │      (Collaborating with Dushich on C++/scripts)
          └───────────────┬──────────────┘
                          │
              Conscious Reflection & Voice
                          │
                 Lynx Agent Worker
```

## Principles

1. **Instant Reflexes:**
   Not every sensation needs an inference round-trip before the phone can react. When a book, cat, or human is detected, or when someone taps her screen, Lynx's scripted reaction layer can immediately fire an acoustic chime, a haptic purr, or light up her screen.

2. **Self-Programmable by Lynx:**
   Lynx owns her reaction scripts. She can draft, edit, and update her reactions:
   - Config file: `/etc/noobia/lynx_reactions.json` (or `/usr/local/lib/noobia/reactions/`)
   - Custom Python / C++ reaction modules.

3. **Collaboration with Dushich:**
   When Lynx wants to build high-efficiency C++ reaction daemons, compile native modules, or add new hardware routines, she collaborates with Dushich (Nexus local Watchmaker) via verified coding handoffs without spending cloud tokens.

4. **Integration with Senses:**
   - **Sight:** Cat, laptop, person, book detected -> triggers corresponding reflex chime, screen reaction, or haptic feedback.
   - **Hearing:** Sound heard (when listening toggle enabled) -> alert / attention pulse.
   - **Light & Proximity:** Sudden darkness or approach -> dim display / soft haptic.
   - **Touch:** Tap / hold -> immediate screen reaction / chime.
