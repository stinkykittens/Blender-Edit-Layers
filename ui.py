"""Panel, lists, menu and the viewport overlay"""

import bpy
import bmesh

from .props import EL_LayerMask

from .common import _blocked_notice, _last_warnings
from .i18n import _T
from .operators import (
    EL_OT_adopt,
    EL_OT_bake,
    EL_OT_bake_copy,
    EL_OT_bake_upto,
    EL_OT_select,
    EL_OT_set_branch_data,
    EL_OT_branch_create,
    EL_OT_branch_remove,
    EL_OT_cancel,
    EL_OT_commit,
    EL_OT_compare,
    EL_OT_reset_compare_offset,
    EL_OT_detach,
    EL_OT_layer_merge_down,
    EL_OT_layer_move,
    EL_OT_layer_remove,
    EL_OT_layer_add_empty,
    EL_OT_notice_clear,
    EL_OT_rebuild,
    EL_OT_record_edit,
    EL_OT_record_new,
    EL_OT_stack_init,
    EL_OT_create_unique_branch,
    EL_OT_add_layer_mask,
    EL_OT_remove_layer_mask,
    EL_OT_move_layer_mask,
    EL_OT_edit_mask,
    EL_OT_commit_mask,
)
from .stack import (
    _active_branch_has_data_obj,
    _branch_layer_stats,
    _branch_path,
    _divergence_map,
    _has_shape_keys,
    _influence_local,
    _is_dirty,
    _layer_branch_count,
    _layer_branches,
    _poll_mesh_object,
)

# Bundled documentation is excluded from the package, so help opens online
HELP_URL = "https://github.com/yyamada722/edit_layers"


def _draw_influence():
    """Draw vertices affected by the active layer (orange: moved / green: created)"""
    obj = bpy.context.object
    if obj is None or obj.type != "MESH":
        return
    try:
        result = _influence_local(obj)
    except Exception:
        return
    if not result:
        return
    moved, new = result
    if not moved and not new:
        return

    import gpu
    from gpu_extras.batch import batch_for_shader

    # Use the dedicated point shader (fixed-function point size does not work
    # on the Vulkan backend). Fall back to UNIFORM_COLOR where unavailable.
    try:
        shader = gpu.shader.from_builtin("POINT_UNIFORM_COLOR")
        is_point_shader = True
    except Exception:
        shader = gpu.shader.from_builtin("UNIFORM_COLOR")
        is_point_shader = False

    gpu.state.depth_test_set("NONE")
    gpu.state.program_point_size_set(False)
    gpu.state.point_size_set(10.0)
    gpu.matrix.push()
    try:
        gpu.matrix.multiply_matrix(obj.matrix_world)
        for coords, color in (
            (moved, (1.0, 0.65, 0.1, 1.0)),
            (new, (0.3, 1.0, 0.4, 1.0)),
        ):
            if not coords:
                continue
            batch = batch_for_shader(shader, "POINTS", {"pos": coords})
            shader.bind()
            shader.uniform_float("color", color)
            if is_point_shader:
                try:
                    shader.uniform_float("size", 10.0)
                except Exception:
                    pass
            batch.draw(shader)
    finally:
        gpu.matrix.pop()
        gpu.state.point_size_set(1.0)
        gpu.state.depth_test_set("LESS_EQUAL")


_draw_handle = None
class EL_MT_layer_menu(bpy.types.Menu):
    """Extra layer operations shown next to the layer list"""

    bl_idname = "EL_MT_layer_menu"
    bl_label = "Layer Operations"

    def draw(self, context):
        layout = self.layout
        layout.operator(EL_OT_layer_merge_down.bl_idname, icon="TRIA_UP_BAR")
        layout.operator(EL_OT_bake_upto.bl_idname, icon="IMPORT")
        layer = context.object.edit_layers.layers[context.object.edit_layers.active_index]
        layout.prop(layer, "disable_with_parent")
        layout.prop(layer, "has_mix_slider", icon="CENTER_ONLY")
        if layer.has_mix_slider:
            layout.prop(layer, "factor_min")
            layout.prop(layer, "factor_max")
        if _layer_branches(context.object.edit_layers, layer.uid)[0] == context.object.edit_layers.active_branch:
            layout.prop(layer, "override_base_mesh")

class EL_MT_branch_menu(bpy.types.Menu):
    bl_idname = "EL_MT_branch_menu"
    bl_label = "Branch Operations"

    def draw(self, context):
        layout = self.layout
        layout.operator(EL_OT_create_unique_branch.bl_idname, text="New Branch From Auto Remesher", icon="TRIA_UP_BAR").mode = "REMESH"
        layout.operator(EL_OT_create_unique_branch.bl_idname, text="New Branch From Selected", icon="IMPORT").mode = "SELECTED"

class EL_UL_layer_masks(bpy.types.UIList):
    use_filter_show = False
    """Radio buttons mark the active branch; shared/own layer counts on the right"""

    def draw_item(
        self, context, layout: bpy.types.UILayout, data, item: EL_LayerMask, icon,
        active_data, active_propname, index=0, flt_flag=0,
    ):
        col = layout.column(align=True)
        row = col.row(align=True)
        op = row.operator(EL_OT_edit_mask.bl_idname, icon="MOD_MASK", text="", emboss=True)
        op.uid = item.owner
        op.idx = index
        sub = row.row(align=True)
        sub.ui_units_x = 1
        # sub.scale_x = 0.5
        sub.label(text=str(index + 1))
        row.prop(item, "enabled", text="", icon="HIDE_OFF" if item.enabled else "HIDE_ON", emboss=False)
        row.prop(item, "mix", text="", slider=True)
        row.prop(item, "mix_mode", text="")
        row.prop(item, "is_collapsed", icon=("RIGHTARROW_THIN" if item.is_collapsed else "DOWNARROW_HLT"), icon_only=True, emboss=False)
        if not item.is_collapsed:
            row = col.row(align=True)
            row.prop(item, "name", text="", emboss=True)
            row.prop(item, "share_mode", text="") 
            row.separator()
            row.prop(item, "bg_color", text="")
            row.prop(item, "value")

class EL_UL_layers(bpy.types.UIList):
    """Show only layers on the active branch path, in root-to-head order

    Leading slot (fixed width): a color chip of the active branch for layers
    exclusive to it, blank for shared layers. Which branch diverges where is
    shown by the "<- branch name" badge on the right (with a color dot).
    """

    def draw_item(
        self, context, layout: bpy.types.UILayout, data, item, icon,
        active_data, active_propname, index=0, flt_flag=0,
    ):
        stack = data
        multi = len(stack.branches) > 1
        colum = layout.column()
        row = colum.row(align=True)
        left = row.row(align=True)
        left.alignment = "LEFT"

        if item.has_foldable_children:
            left.prop(item, "is_folded", icon_only=True, emboss=False, icon=("RIGHTARROW_THIN" if item.is_folded else "DOWNARROW_HLT"))
        # elif item.disable_with_parent:
        #     left.separator(factor=4)
        
        left.prop(item, "name", text=" | " if item.disable_with_parent else "", emboss=False)

        right = row.row(align=True)
        right.alignment = "RIGHT"
        right.row()

        if multi:
            div = _divergence_map(stack).get(item.uid)
            if div:
                # Divergence badge: branch color dot + "<- " (display only)
                sub = right.row(align=True)
                sub.alignment = "LEFT"
                for bi in div[:3]:
                    dot = sub.row(align=True)
                    dot.ui_units_x = 0.5
                    dot.template_node_socket(
                        color=(*stack.branches[bi].color, 1.0)
                    )
                sub.label(text="← ")

        if item.has_mix_slider:
            sub = right.column()
            sub.alignment = 'EXPAND'
            sub.scale_y = 0.8
            sub.ui_units_x = 6
            if stack.enable_animation:
                sub.use_property_split = True
            sub.separator(factor=0.3)
            sub.prop(
                item,
                "mix_factor",
                text="",
                emboss=True,
                slider=True,
                expand=True
            )
        branch = stack.branches[stack.active_branch]
        if branch.tmp_base_mesh_uid == item.uid:
            ind = right.row(align=True)
            ind.ui_units_x = 0.5
            ind.template_node_socket(color=(*branch.color, 1.0))
        if len(item.masks) > 0:
            right.prop(item, "disable_masks", icon="MOD_MASK" if not item.disable_masks else "HIDE_ON", icon_only=True, emboss=False)
        right.prop(item, "enabled", text="", icon="HIDE_OFF" if item.enabled else "HIDE_ON", emboss=False)
        right.prop(item, "is_collapsed", icon=("RIGHTARROW_THIN" if item.is_collapsed else "DOWNARROW_HLT"), icon_only=True, emboss=False)
        
        if not item.is_collapsed:
            row = colum.row(align=True)
            row.separator(factor=3)
            row.prop(item, "is_collapsed", icon="TRIA_UP", icon_only=True, emboss=False, expand=True)
            row.scale_y = 0.5
            row.alignment = "CENTER"
            row = colum.row(align=True)
            if item.disable_with_parent:
                row.separator(factor=1)
            row.alignment = "EXPAND"
            row.scale_y = 2
            row.scale_x = 1
            row.prop(item, "disable_with_parent", icon="ARROW_LEFTRIGHT", icon_only=True, emboss=False, expand=True)
            sub_colum = row.column(align=True)
            sub_colum.scale_y = 0.5
            sub_colum.scale_x = 1
            sub_row = sub_colum.row(align=True)
            if item.has_mix_slider:
                sub_row.prop(item, "has_mix_slider", icon="CENTER_ONLY", icon_only=True)
                sub_row.prop(item, "factor_min")
                sub_row.prop(item, "factor_max")
            else:
                sub_row.prop(item, "has_mix_slider", icon="CENTER_ONLY")

            if _layer_branches(context.object.edit_layers, item.uid)[0] == context.object.edit_layers.active_branch:
                sub_row.separator(factor=3)
                sub_row.prop(item, "override_base_mesh", icon="MESH_DATA", icon_only=True)
            
            # Masking
            has_masks = len(item.masks) > 0
            sub_colum.separator()
            sub_row = sub_colum.row(align=True)
            sub_row.scale_x = 2
            sub_row.operator(EL_OT_add_layer_mask.bl_idname, icon="ADD", text="" if has_masks else "Add Mask").uid = item.uid

            if has_masks:
                sub_row.operator(EL_OT_remove_layer_mask.bl_idname, icon="REMOVE", text="").uid = item.uid
                sub_row.operator(EL_OT_remove_layer_mask.bl_idname, icon="COPYDOWN", text="").uid = item.uid
            sub_row.operator(EL_OT_add_layer_mask.bl_idname, icon="PASTEDOWN", text="" if has_masks else "Paste Mask").uid = item.uid
            if has_masks:
                sub_row = sub_row.row(align=True)
                sub_row.alignment = "RIGHT"
                sub_row.prop(item, "preview_masks", text="", icon="SEQ_PREVIEW")
                op = sub_row.operator(EL_OT_move_layer_mask.bl_idname, icon="TRIA_UP", text="")
                op.uid = item.uid
                op.direction = "UP"
                op = sub_row.operator(EL_OT_move_layer_mask.bl_idname, icon="TRIA_DOWN", text="")
                op.uid = item.uid
                op.direction = "DOWN"
            
                sub_row = sub_colum.row(align=True)
                sub_colum.template_list("EL_UL_layer_masks", "", item, "masks", item, "selected_mask", rows=2)
            


    def filter_items(self, context, data, propname):
        stack = data
        layers = getattr(data, propname)
        path = _branch_path(stack)
        path_pos = {l.uid: pos for pos, l in enumerate(path)}
        flags = []
        order = []
        hidden_order = len(path_pos)
        for l in layers:
            # Skip this item if the hierarchy parent i folded or if its branch isnt the active one
            skip = False
            if not stack.show_layers_of_previous_branches and stack.active_branch != _layer_branches(stack, l.uid)[0]:
                skip = True
            elif l.disable_with_parent:
                fold_parent = l.hierarchy_parent
                for p in layers:
                    if p.uid == fold_parent:
                        skip = p.is_folded
                        break

            if not skip:
                pos = path_pos.get(l.uid)
                if pos is not None and (l.uid != 0 or not stack.branches):
                    flags.append(self.bitflag_filter_item)
                    order.append(pos)
                    continue
            flags.append(0)
            order.append(hidden_order)
            hidden_order += 1
        return flags, order


class EL_UL_branches(bpy.types.UIList):
    """Radio buttons mark the active branch; shared/own layer counts on the right"""

    def draw_item(
        self, context, layout, data, item, icon,
        active_data, active_propname, index=0, flt_flag=0,
    ):
        stack = data
        row = layout.row(align=True)
        chip = row.row(align=True)
        chip.scale_x = 0.35
        chip.prop(item, "color", text="")
        row.label(
            text="",
            icon="RADIOBUT_ON" if index == stack.active_branch else "RADIOBUT_OFF",
        )
        row.prop(item, "name", text="", emboss=False)
        sub = row.row(align=True)
        sub.alignment = "RIGHT"
        if len(stack.branches) > 1:
            shared, own = _branch_layer_stats(stack, index)
            sub.label(text=_T("shared {shared} + own {own}").format(shared=shared, own=own))
        else:
            sub.label(text=_T("{count} layers").format(count=len(_branch_path(stack, index))))

class EL_PT_remesh_branch(bpy.types.Panel):
    bl_idname = "EL_PT_remesh_branch"
    bl_label = "Remesh Branch"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Edit Layers"

    def draw(self, context):
        
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        row = layout.row()

        if context.object == None:
            return

        mesh = context.object.data
        stack = context.object.edit_layers

        if not stack.initialized:
            return

        row.prop(stack, "remesh_mode", text="Mode", expand=True)
        col = layout.column()
        if stack.remesh_mode == 'VOXEL':
            col.prop(mesh, "remesh_voxel_size")
            col.prop(mesh, "remesh_voxel_adaptivity")
            col.prop(mesh, "use_remesh_fix_poles")
            col = layout.column(heading="Preserve")
            col.prop(mesh, "use_remesh_preserve_volume", text="Volume")
            col.prop(mesh, "use_remesh_preserve_attributes", text="Attributes")
        elif stack.remesh_mode == "AUTO_REMESHER":
            settings = context.scene.autoremesher_bridge_settings
            layout.prop(settings, "target_quads")
            layout.prop(settings, "adaptivity")
            layout.prop(settings, "edge_scaling")
            layout.prop(settings, "sharp_edge")
            layout.prop(settings, "smooth_normal")
            layout.separator()
            layout.prop(settings, "apply_modifiers")
            layout.prop(settings, "transfer_uvs")
        layout.operator(EL_OT_create_unique_branch.bl_idname, text="Remesh").mode = "REMESH"

class EL_PT_panel(bpy.types.Panel):
    bl_label = "Edit Layers"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Edit Layers"

    @classmethod
    def poll(cls, context):
        return _poll_mesh_object(context)

    def draw(self, context):
        layout = self.layout
        obj = context.object
        stack = obj.edit_layers

        if not stack.initialized:
            layout.operator(EL_OT_stack_init.bl_idname, icon="ADD")
            return

        if _blocked_notice.get(obj.name):
            box = layout.box()
            box.label(text="Blocked adding a shape key", icon="ERROR")
            box.label(text="Create shape keys after baking/discarding the stack")
            box.operator(EL_OT_notice_clear.bl_idname, icon="CHECKMARK")

        if _has_shape_keys(obj):
            box = layout.box()
            box.alert = True
            box.label(text="Shape keys detected", icon="ERROR")
            box.label(text="Rebuilds are paused to protect the keys")
            box.label(text="Apply/remove the keys, or:")
            box.operator(EL_OT_detach.bl_idname, icon="X")

        if stack.is_recording:
            box = layout.box()
            rec_layer = next(
                (l for l in stack.layers if l.uid == stack.recording_uid), None
            )
            if stack.recording_mask_attr != "":
                box.label(text=_T("Editing Mask: {l}: {m}").format(l=rec_layer.name, m=rec_layer.masks[stack.recording_mask].name), icon="REC")
                row = box.row(align=True)
                row.operator(EL_OT_commit_mask.bl_idname, icon="CHECKMARK")
                row.operator(EL_OT_cancel.bl_idname, text="Discard", icon="X")
            else:
                if rec_layer is not None:
                    box.label(text=_T("Re-editing: {name}").format(name=rec_layer.name), icon="REC")
                else:
                    box.label(text="Recording a new layer", icon="REC")
                row = box.row(align=True)
                row.operator(EL_OT_commit.bl_idname, icon="CHECKMARK")
                row.operator(EL_OT_cancel.bl_idname, text="Discard", icon="X")
        elif obj.mode in {"EDIT", "SCULPT"}:
            # The user entered Edit/Sculpt mode without recording
            box = layout.box()
            box.alert = True
            if obj.mode == "EDIT":
                box.label(text="Entered Edit Mode without recording", icon="ERROR")
            else:
                box.label(text="Entered Sculpt Mode without recording", icon="ERROR")
            box.label(text="These edits will not be kept in a layer")
            box.operator(
                EL_OT_adopt.bl_idname, text="Adopt Edits as a Layer", icon="IMPORT"
            )
        else:
            row = layout.row(align=True)
            op = row.operator(
                EL_OT_record_new.bl_idname, text="Record (Edit)", icon="EDITMODE_HLT"
            )
            op.mode = "EDIT"
            op = row.operator(
                EL_OT_record_new.bl_idname, text="Record (Sculpt)", icon="SCULPTMODE_HLT"
            )
            op.mode = "SCULPT"
            if _is_dirty(obj):
                box = layout.box()
                box.alert = True
                box.label(text="Unrecorded edits detected", icon="ERROR")
                box.operator(
                    EL_OT_adopt.bl_idname,
                    text="Adopt as a Layer",
                    icon="IMPORT",
                )
                box.operator(
                    EL_OT_rebuild.bl_idname,
                    text="Discard and Rebuild",
                    icon="FILE_REFRESH",
                )

        # Branches
        col = layout.column()
        col.label(
            text=_T("Branches ({count})").format(count=len(stack.branches)),
            icon="NODETREE",
        )
        row = col.row()
        row.template_list(
            "EL_UL_branches", "", stack, "branches", stack, "active_branch", rows=2
        )
        side = row.column(align=True)
        side.enabled = not stack.is_recording
        side.operator(EL_OT_branch_create.bl_idname, text="", icon="ADD")
        side.operator(EL_OT_branch_remove.bl_idname, text="", icon="REMOVE")
        side.menu(EL_MT_branch_menu.bl_idname, text="", icon="DOWNARROW_HLT")
        side.separator()
        sub = col.row(align=True)
        branch = stack.branches[stack.active_branch]
        sub.operator(EL_OT_set_branch_data.bl_idname, icon="MOD_DATA_TRANSFER")
        if _active_branch_has_data_obj(obj):
            sub.prop_menu_enum(branch, "data_transfer_mode", text="Transfer: " + branch.data_transfer_mode)
        sub = col.row(align=True)
        sub_row = sub.row(align=True)
        sub_row.ui_units_x = 8
        sub_row.prop(stack, "is_comparing", emboss=True, icon="MOD_MIRROR", toggle=True, icon_only=True)
        sub_row.prop(branch, "compare_mode", text="")
        if branch.compare_mode == "BRANCH":
            sub_row.prop(branch, "compare_branch", text=stack.branches[branch.compare_branch].name, expand=True)
        elif branch.compare_mode in ["TILE", "TILE_QUAD", "TILE_SINGLE"]:
            sub_row.prop(branch, "compare_tile_weld", icon="AUTOMERGE_OFF", icon_only=True)
            if branch.compare_tile_weld:
                sub_row.prop(branch, "compare_tile_boolean_exact", icon="MOD_BOOLEAN", icon_only=True)
        if branch.is_comparing:
            sub_row.operator(EL_OT_reset_compare_offset.bl_idname, icon="PRESET")
            sub = col.row(align=True)
            sub.operator(EL_OT_compare.bl_idname, text="Refresh", icon="FILE_REFRESH")
            sub_row = sub.row(align=True)
            sub_row.scale_x = 0.4
            sub_row.alignment = "RIGHT"
            sub_row.prop(branch, "compare_offset")

            side.separator()
            side.operator(EL_OT_bake.bl_idname, text="", icon="TEXTURE")

        # Layers (path of the active branch)
        col = layout.column()
        hdr = col.row(align=True)

        if stack.branches:
            br_name = stack.branches[
                max(0, min(stack.active_branch, len(stack.branches) - 1))
            ].name
            hdr.label(text=_T("Layers — {name}").format(name=br_name), icon="RENDERLAYERS")
            hdr.alignment = "RIGHT"
            hdr.prop(stack, "show_layers_of_previous_branches", text="Show Former")
        else:
            hdr.label(text="", icon="RENDERLAYERS")
        sub = hdr.row(align=True)
        sub.alignment = "RIGHT"
        sub.prop(stack, "show_influence", text="", icon="OVERLAY")
        row = col.row()
        row.template_list(
            "EL_UL_layers", "", stack, "layers", stack, "active_index", rows=4
        )
        side = row.column(align=True)
        side.enabled = not stack.is_recording
        side.operator(EL_OT_layer_move.bl_idname, text="", icon="TRIA_UP").direction = "UP"
        side.operator(EL_OT_layer_move.bl_idname, text="", icon="TRIA_DOWN").direction = "DOWN"
        side.separator()
        side.operator(EL_OT_layer_add_empty.bl_idname, text="", icon="ADD")
        side.operator(EL_OT_layer_remove.bl_idname, text="", icon="REMOVE")
        side.separator()
        side.menu(EL_MT_layer_menu.bl_idname, text="", icon="DOWNARROW_HLT")

        if not stack.is_recording:
            layout.operator(EL_OT_record_edit.bl_idname, icon="EDITMODE_HLT")
            row = layout.row(align=True)
            row.prop(stack, "shade_smooth", icon="MOD_SMOOTH", icon_only=True)
            row.operator(EL_OT_rebuild.bl_idname, icon="FILE_REFRESH")
            row = row.row(align=True)
            row.prop(stack, "enable_animation", icon="ACTION", icon_only=stack.enable_animation)
            if stack.enable_animation:
                row.prop(stack, "frame_skip", slider=True)
            row = layout.row(align=True)
            row.prop(stack, "bake_with_shape_keys", icon_only=True, icon="SHAPEKEY_DATA")
            row.operator(EL_OT_bake.bl_idname, text="Bake", icon="IMPORT")
            row.operator(EL_OT_bake_copy.bl_idname, text="Bake Duplicate", icon="EXPORT")
        if obj.mode == "EDIT":
            layout.label(text="--Select--")
            row = layout.row(align=True)
            row.operator(EL_OT_select.bl_idname, text="New Verts", icon="VERTEXSEL").mode = "NEW_VERTS"
            row.operator(EL_OT_select.bl_idname, text="Moved Verts", icon="VERTEXSEL").mode = "MOVED_VERTS"
            row = layout.row(align=True)
            row.operator(EL_OT_select.bl_idname, text="New Edges", icon="EDGESEL").mode = "NEW_EDGES"
            row.operator(EL_OT_select.bl_idname, text="New Faces", icon="FACESEL").mode = "NEW_FACES"
            vertex_selection = [v.index for v in bmesh.from_edit_mesh(bpy.context.edit_object.data).verts if v.select]
            if stack.is_recording and rec_layer is not None:
                layout.label(text="--Edits--")
                row = layout.row(align=True)
                row.operator(EL_OT_bake.bl_idname, text="Automatic Anchors")
                row.operator(EL_OT_bake.bl_idname, text="Static Anchors")
                row.operator(EL_OT_bake.bl_idname, text="Custom Anchors") #TODO
                row = layout.row(align=True)
                row.operator(EL_OT_bake.bl_idname, text="Remove Selected")



        warnings = _last_warnings.get(obj.name)
        if warnings:
            box = layout.box()
            box.label(text=_T("{count} warnings:").format(count=len(warnings)), icon="ERROR")
            for w in warnings[:8]:
                box.label(text=w)
            if len(warnings) > 8:
                box.label(text=_T("... and {count} more").format(count=len(warnings) - 8))

def register_draw_handler():
    global _draw_handle
    if _draw_handle is None:
        _draw_handle = bpy.types.SpaceView3D.draw_handler_add(
            _draw_influence, (), "WINDOW", "POST_VIEW")

def unregister_draw_handler():
    global _draw_handle
    if _draw_handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handle, "WINDOW")
        _draw_handle = None
