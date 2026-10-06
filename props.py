"""Property group definitions and update callbacks"""

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    FloatVectorProperty,
    IntVectorProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
    EnumProperty,
)

from .stack import _has_shape_keys, _is_dirty, _layer_branches, _rebuild

def _tag_redraw_view3d(context):
    for win in context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def _on_enabled_update(self, context):
    obj = context.object
    if obj and obj.type == "MESH":
        stack = obj.edit_layers
        # Defer rebuilds while unrecorded edits exist (do not overwrite them).
        # Also defer while shape keys exist (a rebuild would destroy them).
        if (
            stack.initialized
            and not stack.is_rebuilding
            and not stack.is_recording
            and not _is_dirty(obj)
            and not _has_shape_keys(obj)
        ):
            _rebuild(obj)

def _branch_update(self, context):
    obj = context.object
    if obj and obj.type == "MESH":
        stack = obj.edit_layers
        if (
            stack.initialized
            and not stack.is_rebuilding
            and not stack.is_recording
            and stack.branches
            and not _is_dirty(obj)
            and not _has_shape_keys(obj)
        ):
            _rebuild(obj, rebuild_br_base_meshes=True)

def _mask_update(self, context):
    if self.share_mode == "UNIQUE":
        _on_enabled_update(self, context)
    obj = context.object
    if obj and obj.type == "MESH":
        stack = obj.edit_layers
        if (
            stack.initialized
            and not stack.is_rebuilding
            and not stack.is_recording
            and stack.branches
            and not _is_dirty(obj)
            and not _has_shape_keys(obj)
        ):
            _rebuild(obj, rebuild_br_base_meshes=True, shared_mask_update=True)

def _set_enabled(self, v):
    self.internal_enabled = v

def _get_enabled(self):
    if not self.internal_enabled:
        return False
    if self.disable_with_parent:
        hierarchy_parent = _get_hierarchy_parent(self)
        for l in bpy.context.object.edit_layers.layers:
            if l.uid == hierarchy_parent:
                return l.enabled
    return self.internal_enabled

def _get_hierarchy_parent(self):
    if not self.disable_with_parent:
        return -1
    for l in bpy.context.object.edit_layers.layers:
        if l.uid == self.parent:
            if not l.disable_with_parent:
                return l.uid
            else:
                return _get_hierarchy_parent(l)
    return -1

def _get_has_foldable_children(self):
    for l in bpy.context.object.edit_layers.layers:
        if l.hierarchy_parent == self.uid:
            return True
    return False

def _get_override_base_mesh(self):
    stack = bpy.context.object.edit_layers
    return stack.branches[stack.active_branch].tmp_base_mesh_uid == self.uid

def _set_override_base_mesh(self, v):
    stack = bpy.context.object.edit_layers

    if stack.branches[stack.active_branch].tmp_base_mesh_uid == self.uid and not v:
        stack.branches[stack.active_branch].tmp_base_mesh_uid = -1
    elif v and _layer_branches(stack, self.uid)[0] == stack.active_branch:
        stack.branches[stack.active_branch].tmp_base_mesh_uid = self.uid

def _set_comparing(self, v):
    self.branches[self.active_branch].is_comparing = v
    if v:
        bpy.ops.edit_layers.compare()
    else:
        bpy.ops.edit_layers.compare_clear()

def _get_comparing(self):
    return self.branches[self.active_branch].is_comparing

def _update_compare(self, context):
    if self.is_comparing:
        bpy.ops.edit_layers.compare()
    else:
        bpy.ops.edit_layers.compare_clear()

def _get_compare_branch_name(self):
    for i, br in enumerate(bpy.context.object.edit_layers.branches):
        if i == self.compare_branch:
            return br.name
    return self.name

def _set_compare_branch_name(self, v):
    for i, br in enumerate(bpy.context.object.edit_layers.branches):
        if br.name == v:
            self.compare_branch = i
    
def _get_shared_mask_names(self, context):
    shared = []
    for l in context.object.edit_layers.layers:
        for m in l.masks:
            if m.share_mode == "SHARE":
                shared.append((m.name, m.name, ""))
    return shared

def _update_shared_mask_name(self, context):
    self.name = self.shared_name


class EL_LayerMask(bpy.types.PropertyGroup):
    owner: IntProperty()
    name: StringProperty(default="Mask", update=_mask_update)
    shared_name: EnumProperty(items=_get_shared_mask_names, update=_update_shared_mask_name)
    mix: FloatProperty(name="Mix", min=0, max=1, default=1, update=_mask_update)
    enabled: BoolProperty(name="Enabled", default=True, update=_mask_update)
    mix_mode: EnumProperty(name="Mix Mode",
                           items=[("MIX", "Mix", ""),("ADD", "Add", ""), ("SUBTRACT", "Subtract", ""), ("MULTIPLY", "Multiply", "")],
                           default="MIX", update=_mask_update)
    value: FloatProperty(name="Value", default=1, update=_mask_update)
    bg_color: FloatVectorProperty(
            name="BG",
            subtype="COLOR",
            size=3,
            min=0.0,
            max=1.0,
            default=(0.0, 0.0, 0.0),
            update=_mask_update)
    data: StringProperty(default="")
    is_collapsed: BoolProperty(default=False)
    share_mode: EnumProperty(items=[("UNIQUE", "Unique", ""), ("SHARE", "Share", ""), ("COPY", "Copy", ""), ("OVERRIDE", "Override", "")], default="UNIQUE",
                             description="Set to 'Branch' or 'Stack' to make the mask share its data with other masks having the same name",
                             update=_mask_update)
    override_data: BoolProperty(default=False, update=_mask_update)
    override_enabled: BoolProperty(default=False, update=_mask_update)
    override_mix: BoolProperty(default=False, update=_mask_update)
    override_mix_mode: BoolProperty(default=False, update=_mask_update)
    override_bg: BoolProperty(default=False, update=_mask_update)
    override_value: BoolProperty(default=False, update=_mask_update)
    shared_mask_not_found: BoolProperty(default=False)

    def copy_data(self, mask):
        if not self.override_data:
            self.data = mask.data
        if not self.override_enabled:
            self.enabled = mask.enabled
        if not self.override_mix:
            self.mix = mask.mix
        if not self.override_mix_mode:
            self.mix_mode = mask.mix_mode
        if not self.override_bg:
            self.bg_color = mask.bg_color
        if not self.override_value:
            self.value = mask.value


#TODO: a way to delete vertexes from the data or edit its anchors; add empty layer; Branch unique slider
class EL_Layer(bpy.types.PropertyGroup):
    name: StringProperty(name="Name", default="Layer")
    enabled: BoolProperty(name="Enabled", default=True, update=_on_enabled_update, get=_get_enabled, set=_set_enabled)
    mix_factor: FloatProperty(name="Mix", min=0, max=1, default=1, update=_on_enabled_update)
    has_mix_slider: BoolProperty(name="Has Mix Slider", default=False)
    factor_min: FloatProperty(name="Factor Min", default=0, update=_on_enabled_update)
    factor_max: FloatProperty(name="Factor Max", default=1, update=_on_enabled_update)
    disable_with_parent: BoolProperty(name="Disable with parent", default=False)
    has_foldable_children: BoolProperty(get=_get_has_foldable_children)
    # Refers to preventing child layers from being visable
    is_folded: BoolProperty(default=False)
    is_collapsed: BoolProperty(default=True)
    # Persistent layer UID (separate from vertex IDs; 0 = unassigned)
    uid: IntProperty(default=0)
    # UID of the parent layer (0 = directly on the base mesh)
    parent: IntProperty(default=0)
    # UID of the parent or grand parent this layer expands/folds and disables with
    hierarchy_parent: IntProperty(default=0, get=_get_hierarchy_parent)
    # Diff JSON
    data: StringProperty(default="")

    masks: CollectionProperty(type=EL_LayerMask)
    selected_mask: IntProperty(default=0)
    disable_masks: BoolProperty(default=False)
    preview_masks: BoolProperty(default=False)

    internal_enabled: BoolProperty(default=True)
    override_base_mesh: BoolProperty(name="Override Base Mesh", get=_get_override_base_mesh, set=_set_override_base_mesh)


class EL_Branch(bpy.types.PropertyGroup):
    name: StringProperty(name="Name", default="Branch")
    # UID of this branch's tip layer (0 = base mesh only)
    head_uid: IntProperty(default=0)
    # Identification color (shown as list chips and divergence badges; click to change)
    color: FloatVectorProperty(
        name="Color",
        subtype="COLOR",
        size=3,
        min=0.0,
        max=1.0,
        default=(0.7, 0.7, 0.7),
    )
    tmp_base_mesh_uid: IntProperty(default=-1, update=_branch_update)
    data_obj: StringProperty(name="Data Object", default="")
    data_transfer_mode: EnumProperty(name="Data Transfer Mode",
        description="Set mapping mode for data transfer.",
        items=[("NEAREST", "Nearest", "Set Data Transfer Mode.\nDefault behaviour."),
        ("TOPOLOGY", "Topology", "Set Data Transfer Mode.\nUseful when topology stays unchanged e.g. for sculpting.")],
        default="NEAREST")
    exclude_from_comparing: BoolProperty(default=False, name="Exclude from comparing all branches")
    is_comparing: BoolProperty(default=False)
    compare_mode: EnumProperty(name="Compare Mode", 
            items=[("ALL", "All Branches", ""), ("BRANCH", "Branch", ""), ("TILE", "Tile", "Compare against self with realtime updates"), ("TILE_BRANCH", "Tile Branch", "Enables Snapping")],
            default="ALL",
            update=_update_compare)
    compare_tile_mode: EnumProperty(name="Tile Mode",
                                    items=[("SINGLE", "Single", ""), ("TILE", "Tile", ""), ("QUAD", "Tile Quad", "")],
                                    update=_update_compare)
    compare_branch: IntProperty(default=-1, update=_update_compare)
    compare_branch_name: StringProperty(default="", set=_set_compare_branch_name, get=_get_compare_branch_name)
    compare_offset: FloatVectorProperty(name="Offset", default=[0, 0, 0], update=_update_compare)
    compare_tile_weld: BoolProperty(default=False, update=_update_compare)
    compare_tile_boolean_exact: BoolProperty(default=False, update=_update_compare)


class EL_Stack(bpy.types.PropertyGroup):
    initialized: BoolProperty(default=False)
    layers: CollectionProperty(type=EL_Layer)
    active_index: IntProperty(default=0)
    branches: CollectionProperty(type=EL_Branch)
    active_branch: IntProperty(default=0, update=_branch_update)
    # Next vertex ID to assign (0 means unassigned, so start from 1)
    next_id: IntProperty(default=1)
    # Next layer UID to assign
    next_uid: IntProperty(default=1)
    is_recording: BoolProperty(default=False)
    is_dirty: BoolProperty(default=False, get=lambda self: _is_dirty(bpy.context.object))
    is_rebuilding: BoolProperty(default=False)
    # UID of the layer being recorded (0 = new layer)
    recording_uid: IntProperty(default=0)
    recording_mask: IntProperty(default=0)
    recording_mask_attr: StringProperty()
    base_mesh: PointerProperty(type=bpy.types.Mesh)
    show_influence: BoolProperty(
        name="Show Influence",
        description=(
            "Highlight vertices affected by the selected layer "
            "(orange: moved, green: created)"
        ),
        default=False,
        update=lambda self, context: _tag_redraw_view3d(context),
    )
    enable_animation: BoolProperty(default=False, name="Enable Animation")
    frame_skip: IntProperty(default=1, min=0, max=10, name="Frame Skip", description="Animation Playback would rebuild the mesh on every single frame, use this to optimize performance.\n0 means no frames get skipped, 1 means every second frame get skipped...")
    bake_with_shape_keys: BoolProperty()
    shade_smooth: BoolProperty(name="Shade Smooth", default=False, update=_on_enabled_update, description="Apply smooth shading after rebuilding the stack.")
    show_layers_of_previous_branches: BoolProperty()
    remesh_mode: EnumProperty(items=[("AUTO_REMESHER", "Auto Remesher", ""), ("VOXEL", "Voxel", "")], default="AUTO_REMESHER")
    tmp_base_mesh_uid: IntProperty(default=-1)
    tmp_base_mesh: PointerProperty(type=bpy.types.Mesh)
    is_comparing: BoolProperty(set=_set_comparing, get=_get_comparing)
    compare_collection: PointerProperty(type=bpy.types.Collection)
