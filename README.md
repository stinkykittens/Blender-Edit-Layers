# Advanced Layer System For Blender

## BETA

The free [b]Edit Layers[/b] addon by Hayashihikaru adds a awesome way of editing your meshes to blender.
You might be familiar with 3ds-max's modifier stack and it's edit-poly modifier.
It is very useful for non-destructive mesh editing. Blender can't do this out of the box. The changes you've made in edit or sculpt mode are instantly baked into your mesh and there is no way to revert those changes.
The Edit Layers Addon fixes that problem by allowing you to make edits on a per layer basis and disabling/enabling those layers.
It's a great starting point. I encourage everyone to try it out, espacially if you've used 3ds-max before. There are also branches so you can organize your layers better.
However there is one major problem, when you want to use e.g. vertex groups, uvs or vertex painting. The data just gets lost everytime the mesh rebuilds.
That is why I have started developing [b]Advanced Layer System For Blender[/b]. My plugin uses the same core princibles but aims to be more robust and it adds some very useful and advanced features that also makes blender a Z-Brush alternative if you want a similar layer system on top of the core layer mechanics.

- Under development
- I am not sure if this will remain free
- I am a game dev and the features I added are targetet to game artists/devs. Though I believe any 3D artist can benefit from this.

## New Features (Currently)
- Expose some properties for custom ui systems like PieMaster.
- Flexible Ways to preserve vertex data and uvs (you can create a data preserve object and set it's mode on a per branch basis. If the branch doesn't have such an object it will use the current mesh wich works on its own but can cause distortion/data loss).
- Mix layers: You can use a slider to blend in layers. You can make changes more subtle or more extreme depending on what you like. You quickly generate lots of interesting variation of a mesh.
- These mix slider can be animated. However the mesh has to rebuild on every frame, so I've also added frame skipping. If you want to animate using mix layers your on the safer side if you use the next feature.
- Bake With Shape Keys: Great for animators. It will bake your mix layers to shape keys.
- Advanced organization of layers with foldout ui and simple parenting system.
## Whats planned???
- Optimize bake times when using branches.
- UI Improvements. Whith branches the layers list gets a bit messy.
- Bake to shape keys and preserve animation data.
- Initialize a Stack on objects with shape keys: Will create mix layers for each shape key and gets rid of them.
- Removing selected vertices from a layer. Vertex Groups can then be used as a simple way of masking.
- Layer masks using V-Paint mode (pretty advanced).
- Pin Vertices on layer. A way to make vertices stay where there should be, no matter what you do with sliders etc.

This addon uses the Free Edit Layers addon by Hayashihikaru for its core logic! Please check it out https://extensions.blender.org/add-ons/edit-layers/
## Edit Layers (Core functionality)

**English** | [日本語](README.ja.md)

A Blender add-on that adds a **non-destructive mesh editing stack**: your manual modeling work is recorded as stackable layers. Edits that change topology (extrude, bevel, subdivide, delete, ...) are captured too, and every layer can be toggled, reordered and re-edited afterwards. You can also **branch** the stack at any layer to explore and compare variations.

![Comparing branches side by side](docs/images/en/viewport_compare.png)

- **Location**: 3D Viewport > Sidebar (N key) > Edit Layers tab
- **Requirements**: Blender 5.0+ / the UI follows Blender's language preference (English and Japanese included)
- **Help**: an illustrated guide is included at [docs/index.html](docs/index.html) (the **?** button at the bottom of the panel opens this page)

## Installation

Available on **Blender Extensions**:
[extensions.blender.org/add-ons/edit-layers](https://extensions.blender.org/add-ons/edit-layers/)
— install it directly from Blender via Preferences > Get Extensions (search for
"Edit Layers"), and receive updates automatically.

Alternatively, download `edit_layers-<version>.zip` from [Releases](../../releases)
and install it via Preferences > Get Extensions > dropdown menu >
**Install from Disk** (Blender 5.0+).

## Basic workflow

1. Select a mesh object and press **Initialize Stack** in the panel
2. Start recording with **Record (Edit)** or **Record (Sculpt)**
3. Model as usual — no special tools required; all standard Edit and Sculpt Mode features work, and you can switch modes freely while recording
4. Press **Commit** to save the session as a single layer
5. When you are done, press **Bake** to apply the result and remove the stack

<img src="docs/images/en/panel_layers.png" alt="Edit Layers panel" width="380">

### Reading the layer list

The list is ordered top to bottom: first layer at the top, newest at the bottom (applied top-down like the modifier stack).

- **Leading color dot** — the layer belongs only to this branch (branch color). A blank slot means the layer is part of the trunk shared by multiple branches
- **"← branch name" badge** — another branch diverges at this layer
- **Eye icon** — enable/disable the layer (the mesh rebuilds instantly)
- Use **▲▼** to reorder, **−** to delete, and **Re-edit Selected Layer** to go back and edit any layer in the middle of the stack

### What gets recorded

- Vertex moves and topology changes (extrude, bevel, subdivide, knife, delete — anything)
- Material assignment, smooth/flat shading, seams, sharp edges, creases and bevel weights
- New geometry (e.g. extrusions) is stored **relative to nearby anchor vertices**, so it follows along when upstream layers reshape the mesh
- Not recorded: UVs and vertex colors (see limitations)

## Influence overlay

![Influence overlay](docs/images/en/viewport_influence.png)

Enable the **overlay icon** on the right of the layer list header to highlight the vertices affected by the selected layer in the viewport: **orange = moved vertices / green = created vertices**. Handy when you forget what a layer did, or before merging/deleting one.

Deleted elements are not shown (they no longer exist), and attribute-only layers have nothing to display.

## Organizing the stack — merge and partial bake

The **▼ menu** next to the layer list offers stack housekeeping:

- **Merge Into Previous** — merge the selected layer into the one directly above it
- **Bake Up To Here** — apply everything up to the selected layer into the base mesh and remove those layers (partial bake). Useful for collapsing the lower part of the stack once it is final

Both come with safety guards: merging shared layers, partial bakes that would orphan other branches, and operations involving disabled layers are blocked.

## Branches — explore and compare variations

1. Select the layer you want to branch from and press **[+]** next to the branch list
2. The new branch becomes active and new commits stack only onto it
3. Click branches in the list to switch instantly. **Compare** places the other branches next to your object as duplicates; **Clear** removes them

- Re-editing a shared upstream layer **propagates to all branches** (they share the same data)
- Deleting shared layers or reordering across a shared layer is blocked for safety
- Deleting a branch removes only the layers **exclusive** to it
- Comparison results you duplicated yourself are kept when you press Clear
- Click the color chip in the branch list to change a branch's identification color

## Rescue for unrecorded edits

<img src="docs/images/en/panel_rescue.png" alt="Unrecorded edits warning" width="380">

If you edit without starting a recording, the unrecorded changes are detected automatically. Press **Adopt as a Layer** to save them retroactively with the same quality as a normal commit. While unrecorded edits exist, operations that would wipe them (recording, reordering, baking, ...) are blocked; they are only discarded when you explicitly press **Discard and Rebuild**.

Detection relies on the rebuild history of the current session, so unrecorded edits made right after reopening a file are not auto-detected (manual adoption still works).

## Shape keys (mutually exclusive)

Shape keys depend directly on vertex indices and **cannot be combined** with the stack:

- A stack cannot be initialized on a mesh that has shape keys (apply/remove them first)
- Adding shape keys while a stack is active is **automatically reverted**, with a notice in the panel
- **Discard Stack (Keep Current Mesh)** removes only the stack while keeping the current mesh and keys, returning you to the normal workflow

Recommended: create shape keys after you finish modeling with Edit Layers and bake the stack.

## Limitations

- Anchor following for new geometry covers translation only (offsets do not rotate with upstream rotation/scale)
- UVs and vertex colors are not recorded
- Sculpt Dyntopo / remeshing replaces the whole topology and produces very large layers (nothing breaks, though)
- Multiresolution modifier displacement is not recorded
- Closing Blender while recording loses that recording session (committed layers are saved in the .blend)

## Where the data lives

| Data                  | Location                                                |
| --------------------- | ------------------------------------------------------- |
| Layer stack           | `Object.edit_layers` (saved in the .blend)              |
| Base mesh             | `<mesh name>_el_base` (Mesh datablock with a fake user) |
| Persistent vertex IDs | `el_id` INT attribute on the mesh (POINT domain)        |

If anything looks wrong, the **Rebuild** button re-applies the stack. Broken references are reported as warnings at the bottom of the panel and the affected parts are skipped (no crashes).

## Development

See [DEVELOPMENT.md](DEVELOPMENT.md) for build, test and Blender Extensions submission notes.

## License

GPL-3.0-or-later
