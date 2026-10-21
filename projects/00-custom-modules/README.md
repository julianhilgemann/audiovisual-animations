# Custom modules

Reusable TouchDesigner components that the projects in `projects/` share. Each module is one COMP saved as a `.tox`. A project loads it through the COMP's External .tox parameter instead of keeping its own copy, so a change saved here reaches every project the next time it opens.

To turn a feature of a project into a new module, start with `LEARNINGS.md`: the step-by-step recipe from the first extraction, and the TouchDesigner and Embody behaviour it depends on.

| Module | What it is | Used by |
|---|---|---|
| `source-deck/` | Video and audio inputs with a transport. Picture from the camera, a movie file, an external TOP or a YouTube download; sound from the microphone, an audio file, an external CHOP or YouTube. Both can be scrubbed, linked when they come from the same clip and separate otherwise. | `ferroscope` |

## Using a module in a project

1. Add a Base COMP, or drag the module's `.tox` into the network.
2. On its Common page, set External .tox Path to the module's `.tox` relative to the project folder (for a project in `projects/`, `../00-custom-modules/source-deck/source_deck.tox`), and turn Enable External .tox on and both Reload Custom Parameters and Reload Built-In Parameters off.
   With the reloads off, the project's own settings (values and bindings) stay on the instance in its `.toe`, while the network inside always comes from the `.tox`. Parameters a module gains later still appear. Because TD keeps the instance's own parameter definitions, a changed label, help text or menu on an existing parameter may not reach a project that already has the module; re-adding the module picks it up.
3. To show the module's controls on the project's own panel, give the host COMP parameters with the same names and bind each module parameter to the host's (bind expression `parent.Ferro.par.Videosource` in ferroscope). The host's parameter callback presses the module's pulses (`op('source_deck').par.Videorestart.pulse()`).

## Changing a module

Edit the module inside any project that uses it, then press Save Module on its Module page. That writes, into the module's folder:

- `<name>.tox`, the module itself: a clean copy with default values and no bindings to the project it was saved from.
- `<name>.tdxn` and one `.py` per script DAT: text versions for reading and diffing in git. They're output only; editing them changes nothing.

Save Module before the project closes or the module reloads. Saving the project's `.toe` doesn't save the module, and the next open loads the `.tox` again. Other open projects pick the change up when they reopen, or when you pulse Enable External .tox on the module's Common page.

## Embody

Modules carry the `tdxn_exclude` tag, so a host project's Embody leaves them out of its `.tdxn`. The host's file still records the wires to and from them.
