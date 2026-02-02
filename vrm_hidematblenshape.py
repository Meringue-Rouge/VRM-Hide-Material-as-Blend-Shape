bl_info = {
    "name": "VRM Material Hide Shape Key",
    "author": "Meringue Rouge (adapted by Grok)",
    "version": (1, 0),
    "blender": (4, 2, 0),
    "location": "View 3D > UI > VRM",
    "description": "Creates a shape key that hides/shrinks parts using selected materials. Value 0 = normal/visible, Value 1 = shrunk/hidden.",
    "category": "Object",
}

import bpy
import bmesh
from mathutils import Vector

# ------------------------------------------------------------
# Material checkbox item
# ------------------------------------------------------------

class VRMHideMaterialItem(bpy.types.PropertyGroup):
    material: bpy.props.PointerProperty(type=bpy.types.Material)
    use_hide: bpy.props.BoolProperty(name="Use for Hide", default=True)

# ------------------------------------------------------------
# Sync material list
# ------------------------------------------------------------

def sync_material_list(obj):
    if not obj or obj.type != 'MESH':
        return

    obj.vrm_hide_materials.clear()
    for mat in obj.data.materials:
        if mat:
            item = obj.vrm_hide_materials.add()
            item.material = mat
            item.use_hide = True

class SyncMaterialsOperator(bpy.types.Operator):
    bl_idname = "object.sync_hide_materials"
    bl_label = "Refresh Material List"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Update the material list from the active object"

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh object.")
            return {'CANCELLED'}
        
        sync_material_list(obj)
        self.report({'INFO'}, f"Material list updated: {len(obj.vrm_hide_materials)} materials found")
        return {'FINISHED'}

# ------------------------------------------------------------
# Main operator: Create hide shape key
# ------------------------------------------------------------

class CreateHideOperator(bpy.types.Operator):
    bl_idname = "object.create_material_hide"
    bl_label = "Create Hide Shape Key"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Creates a shape key where value 0 = normal/visible and value 1 = shrunk/hidden (requires no existing shape keys)"

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh object.")
            return {'CANCELLED'}

        # Do not allow if shape keys already exist
        if obj.data.shape_keys:
            self.report({'ERROR'}, "Object already has shape keys. Remove them first (this addon resets the basis).")
            return {'CANCELLED'}

        checked_indices = [
            i for i, item in enumerate(obj.vrm_hide_materials)
            if item.use_hide and item.material
        ]

        if not checked_indices:
            self.report({'ERROR'}, "No materials selected for hide.")
            return {'CANCELLED'}

        key_name = context.scene.hide_shape_key_name.strip()
        if not key_name:
            key_name = "Hidden"

        factor = context.scene.hide_shrink_factor
        center_mode = context.scene.hide_shrink_center

        # Find affected vertices
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        affected_verts = set()
        for face in bm.faces:
            if face.material_index in checked_indices:
                for vert in face.verts:
                    affected_verts.add(vert.index)
        bm.free()

        if not affected_verts:
            self.report({'ERROR'}, "No vertices found for selected materials.")
            return {'CANCELLED'}

        # Store original coordinates
        orig_cos = [v.co.copy() for v in obj.data.vertices]

        # Compute shrink center
        if center_mode == 'CENTROID':
            aff_cos = [orig_cos[i] for i in affected_verts]
            center = sum(aff_cos, Vector()) / len(aff_cos)
        else:  # ORIGIN
            center = Vector((0, 0, 0))

        # Compute shrunk coordinates
        shrunk_cos = orig_cos[:]
        for i in affected_verts:
            direction = orig_cos[i] - center
            shrunk_cos[i] = center + direction * factor

        # Create Basis (normal state)
        obj.shape_key_add(name="Basis", from_mix=False)

        # Apply shrunk positions temporarily
        for i, v in enumerate(obj.data.vertices):
            v.co = shrunk_cos[i]
        obj.data.update()

        # Create the hide shape key (shrunk state)
        hide_sk = obj.shape_key_add(name=key_name, from_mix=False)
        hide_sk.value = 0.0  # Default to visible/normal

        # Revert to original positions
        for i, v in enumerate(obj.data.vertices):
            v.co = orig_cos[i]
        obj.data.update()

        self.report({'INFO'}, f"Hide shape key '{key_name}' created! 0 = visible/normal, 1 = hidden/shrunk.")
        return {'FINISHED'}

# ------------------------------------------------------------
# UI Panel
# ------------------------------------------------------------

class HidePanel(bpy.types.Panel):
    bl_label = "VRM Material Hide Shape Key"
    bl_idname = "OBJECT_PT_vrm_material_hide"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "VRM"

    def draw(self, context):
        layout = self.layout
        obj = context.active_object

        if not obj or obj.type != 'MESH':
            layout.label(text="Select a mesh object")
            return

        layout.prop(context.scene, "hide_shape_key_name")
        layout.prop(context.scene, "hide_shrink_factor")
        layout.prop(context.scene, "hide_shrink_center")

        box = layout.box()
        box.label(text="Materials to Hide/Shrink")
        box.operator("object.sync_hide_materials", icon='FILE_REFRESH')

        for item in obj.vrm_hide_materials:
            if item.material:
                row = box.row()
                row.prop(item, "use_hide", text="")
                row.label(text=item.material.name)

        layout.operator("object.create_material_hide", icon='SHAPEKEY_DATA')

# ------------------------------------------------------------
# Registration
# ------------------------------------------------------------

classes = (
    VRMHideMaterialItem,
    SyncMaterialsOperator,
    CreateHideOperator,
    HidePanel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Object.vrm_hide_materials = bpy.props.CollectionProperty(type=VRMHideMaterialItem)

    bpy.types.Scene.hide_shape_key_name = bpy.props.StringProperty(
        name="Shape Key Name",
        description="Name of the created hide shape key",
        default="Hidden"
    )

    bpy.types.Scene.hide_shrink_factor = bpy.props.FloatProperty(
        name="Hidden Scale",
        description="Scale of the part when hidden (0 = collapse to point, 0.01 = very small)",
        default=0.01,
        min=0.0,
        max=1.0,
        subtype='FACTOR'
    )

    bpy.types.Scene.hide_shrink_center = bpy.props.EnumProperty(
        name="Shrink Center",
        items=(
            ('CENTROID', "Part Centroid", "Shrink toward the geometric center of the affected part"),
            ('ORIGIN', "Object Origin", "Shrink toward the object's origin point")
        ),
        default='CENTROID'
    )

def unregister():
    del bpy.types.Object.vrm_hide_materials
    del bpy.types.Scene.hide_shape_key_name
    del bpy.types.Scene.hide_shrink_factor
    del bpy.types.Scene.hide_shrink_center

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()