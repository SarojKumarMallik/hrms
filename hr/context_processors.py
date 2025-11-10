# In context_processors.py
from hr.models import Role, Employee, YsMenuMaster, YsMenuLinkMaster, YsMenuRoleMaster, YsUserRoleMaster

# In context_processors.py
def dynamic_menu(request):
    """Provide menus based on user permissions"""
    if not request.session.get('user_authenticated'):
        return {}

    try:
        user_role_name = request.session.get('user_role')
        user_employee_id = request.session.get('user_employee_id')
        
        # Get role permissions
        try:
            user_role = Role.objects.get(name=user_role_name)
            role_permissions = YsMenuRoleMaster.objects.filter(
                userRoleId=user_role.id, 
                permission_type='ROLE',
                status=True
            )
        except Role.DoesNotExist:
            role_permissions = []

        # Get individual permissions if employee ID exists
        individual_permissions = []
        if user_employee_id:
            try:
                employee = Employee.objects.get(employee_id=user_employee_id)
                individual_permissions = YsMenuRoleMaster.objects.filter(
                    userRoleId=employee.id,
                    permission_type='EMPLOYEE', 
                    status=True
                )
            except Employee.DoesNotExist:
                individual_permissions = []

        # Combine permissions
        all_permissions = list(role_permissions) + list(individual_permissions)
        
        # Build menu structure (same as before)
        menu_dict = {}
        
        for permission in all_permissions:
            if permission.menu_id:
                try:
                    menu = YsMenuMaster.objects.get(menu_id=permission.menu_id, status=1)
                    if menu.menu_id not in menu_dict:
                        menu_dict[menu.menu_id] = {
                            'id': menu.menu_id,
                            'name': menu.menu_name,
                            'icon': menu.menu_icon,
                            'url': menu.menu_url,
                            'submenus': []
                        }
                except YsMenuMaster.DoesNotExist:
                    continue
        
        for permission in all_permissions:
            if permission.menu_link_id:
                try:
                    menu_link = YsMenuLinkMaster.objects.get(menu_link_id=permission.menu_link_id, status=1)
                    menu = menu_link.menu
                    if menu.menu_id in menu_dict:
                        existing_links = [sm.menu_link_id for sm in menu_dict[menu.menu_id]['submenus']]
                        if menu_link.menu_link_id not in existing_links:
                            menu_dict[menu.menu_id]['submenus'].append(menu_link)
                except (YsMenuLinkMaster.DoesNotExist, YsMenuMaster.DoesNotExist):
                    continue
        
        menu_data = list(menu_dict.values())
        menu_data.sort(key=lambda x: x['id'])

        return {'menu_data': menu_data}
    except Exception as e:
        print(f"Menu error: {e}")
        return {'menu_data': []}


def get_assigned_menus(request):
    """
    Context processor to get menus assigned to the logged-in user
    """
    if not request.session.get('user_authenticated'):
        return {'menu_data': []}
    
    try:
        # Get current user's role
        user_role = request.session.get('user_role')
        if not user_role:
            return {'menu_data': []}
        
        # Get user role ID from ys_user_role_master
        user_role_obj = Role.objects.filter(name=user_role, is_active=True).first()
        if not user_role_obj:
            return {'menu_data': []}
        
        role_id = user_role_obj.id
        
        # Get all assigned menu links for this role
        assigned_permissions = YsMenuRoleMaster.objects.filter(
            userRoleId=role_id,
            status=True
        )
        
        # Get assigned menu_link_ids
        assigned_menu_link_ids = [perm.menu_link_id for perm in assigned_permissions]
        
        # Get all active menus
        menus = YsMenuMaster.objects.filter(status=True).order_by('seq')
        
        menu_data = []
        
        for menu in menus:
            # Check if this menu has any assigned submenus
            assigned_submenus = YsMenuLinkMaster.objects.filter(
                menu_id=menu.menu_id,
                menu_link_id__in=assigned_menu_link_ids,
                status=1
            ).order_by('seq')
            
            # Check if this menu itself is assigned (standalone menu)
            is_menu_assigned = YsMenuRoleMaster.objects.filter(
                userRoleId=role_id,
                menu_id=menu.menu_id,
                menu_link_id=menu.menu_id,  # For standalone menus
                status=True
            ).exists()
            
            # If it's a standalone menu and assigned, or has assigned submenus
            if is_menu_assigned or assigned_submenus.exists():
                menu_info = {
                    'id': menu.menu_id,
                    'name': menu.menu_name,
                    'icon': menu.menu_icon,
                    'url': menu.menu_url,
                    'submenus': []
                }
                
                # Add submenus if any are assigned
                for submenu in assigned_submenus:
                    menu_info['submenus'].append({
                        'menu_link_id': submenu.menu_link_id,
                        'menu_link_name': submenu.menu_link_name,
                        'menu_link_icon': submenu.menu_link_icon,
                        'menu_link_url': submenu.menu_link_url
                    })
                
                menu_data.append(menu_info)
        
        return {'menu_data': menu_data}
    
    except Exception as e:
        print(f"Error in menu context processor: {e}")
        return {'menu_data': []}