# Katana Shot Assembly Skill (katana_shot_assembly_skill.md)

> Part of the katana-mcp skill pack. Load this document before building any
> shot-assembly node graph (asset referencing, scene-tree composition,
> camera/edit alignment). All node types, parameter paths and API calls below
> were extracted from the official Katana 9.0v1 demo projects
> (`NAPO__NativeUSD_Full_Multi-Shot_Example`, `import_build_usd_stage`,
> `crowd_system_main`, `turntable_project`, `instancing`) and verified against
> a live Katana 9.0v1 session.

## 1. Core Topology & Data Flow

The standard assembly backbone (seen in every official multi-asset example):

```
[per-asset import branch]  Alembic_In / UsdIn / UsdReferenceSet
            │                     (one branch per asset, named ENV_* / PROP_* / CHAR_*)
            ▼
[per-asset edit stack]   GroupStack / AttributeSet / Transform3D / UsdTransformSet
            │
            ▼
[shot switch (optional)] Switch / VariableSwitch (driven by GSV "shot")
            │
            ▼
        Merge  ◄── CameraCreate or UsdIn (shot camera branch)
            │
            ▼
   Isolate / Prune (optional masking)  →  downstream LookDev / Lighting
```

Key conventions mined from the NAPO multi-shot example:

- **Class locations first**: assets are referenced under `/_CLASS/_ENV/_env_house`,
  `/_CLASS/_PROP/_prop_armchair`, then instanced/arranged into
  `/root/world/geo/...`. Keep reference targets off `/root/world` so class
  prims never render directly.
- **One import node per asset, named by role**: `ENV_house__LOOK`,
  `PROP_armchair__LOOK`, `CHAR_avo__LOOK` — `<ROLE>_<asset>__<PASS>` makes
  GroupStacks self-documenting.
- **Camera is a parallel Merge input**, never daisy-chained through asset
  branches.

## 2. Node Type & Function Registry

| Task | Node type | Key ports | Key parameter paths |
| :--- | :--- | :--- | :--- |
| Alembic import | `Alembic_In` | `out` | `abcAsset`, `name`, `timing.mode` |
| USD import | `UsdIn` | `out` | `fileName`, `name`, `variantSelections` |
| USD reference onto location | `UsdReferenceSet` | `in`, `out` | `location` (target), `reference.mode` = `Paths`, `reference.asset`, `reference.assetPrimPath`, `reference.listPosition` = `prepend`, `reference.timeOffset`, `reference.timeScale` |
| Variant pick | `UsdInVariantSelect` | `in`, `out` | `CEL`, `variantSelection.*` |
| Payload on/off | `UsdPayloadSet` / `UsdActiveSet` | `in`, `out` | `CEL`, `action` |
| Camera | `CameraCreate` | `out` | `name` (e.g. `/root/world/cam/cam_main`), `transform.*`, `fov`, `near`, `far` |
| Per-shot camera from USD | `UsdIn` | `out` | `fileName` expression with `getVar('shot')` |
| Attribute override | `AttributeSet` | `in`, `out` | `CEL`, `attributeName`, `attributeType`, `attributeValue` |
| Transform | `Transform3D` / `UsdTransformSet` | `in`, `out` | `CEL` / `primPath`, `transform.translate|rotate|scale` |
| Scene-tree pruning | `Isolate` (`CEL` + `isolate` 0/1) | `in`, `out` | `CEL`, `isolateFrom` |
| Remove locations | `Prune` | `in`, `out` | `CEL` |
| Static branch select | `Switch` | `i0..iN` (added), `output` | `in` (0-based index, expressionable) |
| GSV branch select | `VariableSwitch` | ports named by GSV value, `out` | `variableName` |
| GSV-gated sub-graph | `VariableEnabledGroup` | `i0`, `out` | `variableName`, `pattern` (e.g. `yes`, `1010`) |
| Ordered edit stack | `GroupStack` | `in`, `out` | children appended via `getChild('__stackInfo')` convention — create children of the GroupStack node directly |
| Scene-state snapshot | `NonpersistentSwitch` | `i0/i1`, `out` | internal to Viewer workflows; do not hand-build |

## 3. Expressions for Shot/Sequence Logic

Verified in the NAPO example (expression DSL, **not** full Python — see
Pitfalls in `katana_lookdev_skill.md`):

```
# Shot-dependent USD file path (on UsdIn.fileName):
project.dir+'/../show/sequences/SE010/USD/shot/shot_C0010_S'+getVar('shot')+'.usda'

# Shot camera:
project.dir+'/../show/sequences/SE010/USD/cam/cam_C0010_S'+getVar('shot')+'.usda'

# Numeric use of a GSV (GSVs are strings — cast with int()):
int(getVar("shot"))

# Frame math in transforms (turntable-style spin, from graph_state_variables_basic):
(frame-1)*4            # degrees per frame on rotate.y

# project.dir is available in every file-path expression; always build
# asset paths from it instead of absolute paths.
```

## 4. Standard Python Construction Blueprint

Runnable inside Katana (GUI session or via katana-mcp). Creates a two-asset
assembly with a class/shot structure, shot-driven USD import, camera and a
GSV switch:

```python
from NodegraphAPI import GetRootNode, CreateNode, SetNodePosition

root = GetRootNode()

# ---- 4.1 per-asset import branches -------------------------------------
def make_reference(parent, name, class_loc, asset_expr, prim_path):
    """UsdReferenceSet: reference a USD asset onto a class location."""
    n = CreateNode('UsdReferenceSet', parent)
    n.setName(name)
    n.getParameter('location').setValue(class_loc, 0)          # target
    n.getParameter('reference.mode').setValue('Paths', 0)
    n.getParameter('reference.asset').setExpression(asset_expr)
    n.getParameter('reference.assetPrimPath').setValue(prim_path, 0)
    n.getParameter('reference.listPosition').setValue('prepend', 0)
    return n

env = make_reference(root, 'ENV_house__LOOK', '/_CLASS/_ENV/_env_house',
                     "project.dir+'/show/USD/env/look/env_house_look.usda'",
                     '/env_house')
prop = make_reference(root, 'PROP_chair__LOOK', '/_CLASS/_PROP/_prop_chair',
                      "project.dir+'/show/USD/prop/look/prop_chair_look.usda'",
                      '/prop_chair')

# ---- 4.2 shot-driven USD import (GSV "shot" must exist, see batch skill) -
usd = CreateNode('UsdIn', root); usd.setName('SHOT_STAGE')
usd.getParameter('fileName').setExpression(
    "project.dir+'/show/sequences/SE010/USD/shot/shot_C0010_S'"
    "+getVar('shot')+'.usda'")

# ---- 4.3 per-shot branch switch -----------------------------------------
sw = CreateNode('VariableSwitch', root); sw.setName('SHOT_SWITCH')
sw.getParameter('variableName').setValue('shot', 0)
# VariableSwitch input ports are NAMED AFTER the GSV value:
for shot in ('1010', '1020', '1040'):
    sw.addInputPort(shot)          # connect each shot branch here
# sw.getInputPort('1010').connect(shot_1010_node.getOutputPort('out'))

# ---- 4.4 camera branch ----------------------------------------------------
cam = CreateNode('CameraCreate', root); cam.setName('CAM_main')
cam.getParameter('name').setValue('/root/world/cam/cam_main', 0)
cam.getParameter('transform.translate.z').setValue(8.0, 0)
cam.getParameter('fov').setValue(40.0, 0)

# USD shot camera alternative:
cam_usd = CreateNode('UsdIn', root); cam_usd.setName('CAM_shot')
cam_usd.getParameter('fileName').setExpression(
    "project.dir+'/show/sequences/SE010/USD/cam/cam_C0010_S'"
    "+getVar('shot')+'.usda'")

# ---- 4.5 merge & masking ---------------------------------------------------
merge = CreateNode('Merge', root); merge.setName('MERGE_ASSETS')
merge.addInputPort('i0').connect(env.getOutputPort('out'))
merge.addInputPort('i1').connect(prop.getOutputPort('out'))
merge.addInputPort('i2').connect(usd.getOutputPort('out'))
merge.addInputPort('i3').connect(cam.getOutputPort('out'))

iso = CreateNode('Isolate', root); iso.setName('ISOLATE_keep_world')
iso.getParameter('CEL').setValue('(/root/world)', 0)   # CEL of what to keep
iso.getInputPort('in').connect(merge.getOutputPort('out'))

for n, pos in ((env, (-600, 200)), (prop, (-600, 50)), (usd, (-600, -100)),
               (sw, (-400, -100)), (cam, (-600, -250)), (cam_usd, (-600, -400)),
               (merge, (-200, 0)), (iso, (0, 0))):
    SetNodePosition(n, pos)
```

## 5. Pitfalls & Gotchas

1. **`Switch` vs `VariableSwitch` port naming**: `Switch` ports are positional
   (`i0`, `i1`, …) selected by the numeric `in` parameter; `VariableSwitch`
   ports are **named after GSV values** (`1010`, `1020`, `single`,
   `threePoint` — real names from the official examples) selected by
   `variableName`. Do not mix the two conventions.
2. **`Merge`/`Switch` start with no input ports** — call `addInputPort()`
   before `connect()` (same pitfall as in the LookDev skill).
3. **GSVs are strings**: arithmetic on a GSV fails silently; wrap with
   `int(getVar("shot"))` (pattern used by the NAPO example itself).
4. **`UsdReferenceSet.location` is the target scene path**, while
   `reference.assetPrimPath` is the prim *inside* the USD file. Reversing
   them produces an empty location with no error.
5. **Class prims must stay outside `/root/world`** (`/_CLASS/...` convention):
   anything under `/root/world` renders. Instance into the world with a
   second reference or `UsdPrimCreate` instead of pointing the class
   reference at a world path.
6. **`Isolate.CEL` selects what to KEEP**, `Prune.CEL` selects what to
   DELETE — opposite semantics, easy to invert.
7. **GroupStack children are ordinary child nodes** of the GroupStack node;
   their execution order is top-to-bottom. The NAPO example names stacks
   `<shot>_<role>__<PASS>` (e.g. `1010_Char__ANIM`) so the shot/role/pass is
   readable from the node name alone.
8. **Always build asset paths from `project.dir`** in expressions. Absolute
   paths break batch renders on farm nodes with different mount points.
9. **NonpersistentSwitch** nodes appear in exported graphs from the official
   demos (hidden Viewer-state helpers). They are not part of the cook for
   rendering — do not route your render chain through them.
