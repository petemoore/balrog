import simplejson as json

from flask import render_template, request, Response, jsonify, make_response

from auslib import dbo
from auslib.admin.views.base import requirelogin, requirepermission, AdminView
from auslib.admin.views.forms import NewPermissionForm, ExistingPermissionForm
from auslib.log import cef_event, CEF_WARN

__all__ = ["UsersView", "PermissionsView", "SpecificPermissionView", "PermissionsPageView", "UserPermissionsPageView"]

def setpermission(f):
    def decorated(*args, **kwargs):
        if kwargs['permission'] != 'admin' and not kwargs['permission'].startswith('/'):
            kwargs['permission'] = '/%s' % kwargs['permission']
        return f(*args, **kwargs)
    return decorated

def permission2selector(permission):
    """Converts a permission to a valid CSS selector."""
    return permission.replace('/', '').replace(':', '')

class UsersView(AdminView):
    """/api/users"""
    def get(self):
        users = dbo.permissions.getAllUsers()
        self.log.debug("Found users: %s", users)
        # TODO: Only return json after old ui is dead
        fmt = request.args.get('format', 'html')
        if fmt == 'json' or 'application/json' in request.headers.get('Accept'):
            # We don't return a plain jsonify'ed list here because of:
            # http://flask.pocoo.org/docs/security/#json-security
            return jsonify(dict(users=users))
        else:
            return render_template('fragments/users.html', users=users.keys())

class PermissionsView(AdminView):
    """/api/users/:username/permissions"""
    def get(self, username):
        permissions = dbo.permissions.getUserPermissions(username)
        # TODO: Only return json after old ui is dead
        fmt = request.args.get('format', 'html')
        if fmt == 'json' or 'application/json' in request.headers.get('Accept'):
            return jsonify(permissions)
        else:
            forms = []
            for perm, values in permissions.items():
                prefix = permission2selector(perm)
                forms.append(ExistingPermissionForm(prefix=prefix, permission=perm, options=values['options'], data_version=values['data_version']))
            return render_template('fragments/user_permissions.html', username=username, permissions=forms)

class SpecificPermissionView(AdminView):
    """/api/users/:username/permissions/:permission"""
    @setpermission
    def get(self, username, permission):
        try:
            perm = dbo.permissions.getUserPermissions(username)[permission]
        except KeyError:
            return Response(status=404)
        # TODO: Only return json after old ui is dead
        fmt = request.args.get('format', 'html')
        if fmt == 'json':
            return jsonify(perm)
        else:
            prefix = permission2selector(permission)
            form = ExistingPermissionForm(prefix=prefix, permission=permission, options=perm['options'], data_version=perm['data_version'])
            return render_template('fragments/permission_row.html', username=username, form=form)

    @setpermission
    @requirelogin
    @requirepermission('/users/:id/permissions/:permission', options=[])
    def _put(self, username, permission, changed_by, transaction):
        try:
            if dbo.permissions.getUserPermissions(username, transaction).get(permission):
                form = ExistingPermissionForm()
                if not form.data_version.data:
                    raise ValueError("Must provide the data version when updating an existing permission.")
                dbo.permissions.updatePermission(changed_by, username, permission, form.data_version.data, form.options.data, transaction=transaction)
                new_data_version = dbo.permissions.getPermission(username=username, permission=permission, transaction=transaction)['data_version']
                return make_response(json.dumps(dict(new_data_version=new_data_version)), 200)
            else:
                form = NewPermissionForm()
                dbo.permissions.grantPermission(changed_by, username, permission, form.options.data, transaction=transaction)
                return make_response(json.dumps(dict(new_data_version=1)), 201)
        except ValueError, e:
            cef_event("Bad input", CEF_WARN, errors=e.args)
            return Response(status=400, response=e.args)

    @setpermission
    @requirelogin
    @requirepermission('/users/:id/permissions/:permission', options=[])
    def _post(self, username, permission, changed_by, transaction):
        if not dbo.permissions.getUserPermissions(username, transaction=transaction).get(permission):
            return Response(status=404)
        try:
            form = ExistingPermissionForm()
            dbo.permissions.updatePermission(changed_by, username, permission, form.data_version.data, form.options.data, transaction=transaction)
            new_data_version = dbo.permissions.getPermission(username=username, permission=permission, transaction=transaction)['data_version']
            return make_response(json.dumps(dict(new_data_version=new_data_version)), 200)
        except ValueError, e:
            cef_event("Bad input", CEF_WARN, errors=e.args)
            return Response(status=400, response=e.args)

    @setpermission
    @requirelogin
    @requirepermission('/users/:id/permissions/:permission', options=[])
    def _delete(self, username, permission, changed_by, transaction):
        if not dbo.permissions.getUserPermissions(username, transaction=transaction).get(permission):
            return Response(status=404)
        try:
            # For practical purposes, DELETE can't have a request body, which means the Form
            # won't find data where it's expecting it. Instead, we have to tell it to look at
            # the query string, which Flask puts in request.args.
            form = ExistingPermissionForm(request.args)
            dbo.permissions.revokePermission(changed_by, username, permission, form.data_version.data, transaction=transaction)
            return Response(status=200)
        except ValueError, e:
            cef_event("Bad input", CEF_WARN, errors=e.args)
            return Response(status=400, response=e.args)



# TODO: Kill me when old admin ui is shut off
class PermissionsPageView(AdminView):
    """/permissions.html"""
    def get(self):
        users = dbo.permissions.getAllUsers()
        return render_template('permissions.html', users=users)

class UserPermissionsPageView(AdminView):
    """/user_permissions.html"""
    def get(self):
        username = request.args.get('username')
        if not username:
            return Response(status=404)
        permissions = dbo.permissions.getUserPermissions(username)
        forms = []
        for perm, values in permissions.items():
            prefix = permission2selector(perm)
            forms.append(ExistingPermissionForm(prefix=prefix, permission=perm, options=values['options'], data_version=values['data_version']))
        return render_template('user_permissions.html', username=username, permissions=forms, newPermission=NewPermissionForm())
