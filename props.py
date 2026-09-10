"""Property group definitions and update callbacks"""

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    FloatVectorProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
    EnumProperty
)

from .stack import _has_shape_keys, _is_dirty, _rebuild


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
            and not stack.is_recording
            and not _is_dirty(obj)
            and not _has_shape_keys(obj)
        ):
            _rebuild(obj)


def _on_branch_switch(self, context):
    obj = context.object
    if obj and obj.type == "MESH":
        stack = obj.edit_layers
        if (
            stack.initialized
            and not stack.is_recording
            and stack.branches
            and not _is_dirty(obj)
            and not _has_shape_keys(obj)
        ):
            _rebuild(obj)


def _set_enabled(self, v):
    self.internal_enabled = v

def _get_enabled(self):
    if not self.internal_enabled:
        return False
    if self.disable_with_parent:
        for l in bpy.context.object.edit_layers.layers:
            if l.uid == self.parent:
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

#TODO: a way to delete vertexes from the data; add empty layer; Branch unique slider
class EL_Layer(bpy.types.PropertyGroup):
    name: StringProperty(name="Name", default="Layer")
    enabled: BoolProperty(name="Enabled", default=True, update=_on_enabled_update, get=_get_enabled, set=_set_enabled)
    mix_factor: FloatProperty(name="Mix", min=0, max=1, default=1, update=_on_enabled_update)
    has_mix_slider: BoolProperty(name="Has Slider", default=False)
    factor_min: FloatProperty(name="Factor Min", default=0, update=_on_enabled_update)
    factor_max: FloatProperty(name="Factor Max", default=1, update=_on_enabled_update)
    disable_with_parent: BoolProperty(name="Disable with parent", default=False)
    has_foldable_children: BoolProperty(get=_get_has_foldable_children)
    is_folded: BoolProperty(default=False)
    # Persistent layer UID (separate from vertex IDs; 0 = unassigned)
    uid: IntProperty(default=0)
    # UID of the parent layer (0 = directly on the base mesh)
    parent: IntProperty(default=0)
    # UID of the parent or grand parent this layer expands/folds and disables with
    hierarchy_parent: IntProperty(default=0, get=_get_hierarchy_parent)
    # Diff JSON
    data: StringProperty(default="") #TODO: pinned vertices; deformation strenght

    internal_enabled: BoolProperty(default=True)


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
    data_obj: StringProperty(name="Data Object", default="")
    data_transfer_mode: EnumProperty(name="Data Transfer Mode", 
        description="Set mapping mode for data transfer.",
        items=[("NEAREST", "Nearest", "Set Data Transfer Mode.\nDefault behaviour."),
        ("TOPOLOGY", "Topology", "Set Data Transfer Mode.\nUseful when topology stays unchanged e.g. for sculpting.")],
        default="NEAREST")


class EL_Stack(bpy.types.PropertyGroup):
    initialized: BoolProperty(default=False)
    layers: CollectionProperty(type=EL_Layer)
    active_index: IntProperty(default=0)
    branches: CollectionProperty(type=EL_Branch)
    active_branch: IntProperty(default=0, update=_on_branch_switch)
    # Next vertex ID to assign (0 means unassigned, so start from 1)
    next_id: IntProperty(default=1)
    # Next layer UID to assign
    next_uid: IntProperty(default=1)
    is_recording: BoolProperty(default=False)
    is_comparing: BoolProperty(default=False)
    is_dirty: BoolProperty(default=False, get=lambda self: _is_dirty(bpy.context.object))
    # UID of the layer being recorded (0 = new layer)
    recording_uid: IntProperty(default=0)
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
    enable_animation: BoolProperty(default=False, name="Animation Enabled")
    frame_skip: IntProperty(default=1, min=0, max=10, name="Frame Skip", description="Animation Playback would rebuild the mesh on every single frame, use this to optimize performance.\n0 means no frames get skipped, 1 means every second frame get skipped...")
