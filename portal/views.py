from flask import (abort, flash, redirect, render_template, request,
                   session, url_for, Markup, jsonify)
import requests, traceback, json, time

try:
    from urllib.parse import urlencode
except ImportError:
    from urllib import urlencode

from portal import app
from portal.decorators import authenticated
from portal.utils import (load_portal_client, get_portal_tokens,
                          get_safe_redirect)
from werkzeug.exceptions import HTTPException
# Use these four lines on container
import sys
import datetime

sys.path.insert(0, '/etc/ci-connect/secrets')

try:
    f = open("/etc/ci-connect/secrets/ciconnect_api_token.txt", "r")
    g = open("/etc/ci-connect/secrets/ciconnect_api_endpoint.txt", "r")
except:
    # Use these two lines below on local
    f = open("secrets/ciconnect_api_token.txt", "r")
    g = open("secrets/ciconnect_api_endpoint.txt", "r")

ciconnect_api_token = f.read().split()[0]
ciconnect_api_endpoint = g.read().split()[0]

try:
    j = open("/etc/ci-connect/secrets/mailgun_api_token.txt", "r")
except:
    j = open("secrets/mailgun_api_token.txt", "r")

mailgun_api_token = j.read().split()[0]

# Create a custom error handler for Exceptions
@app.errorhandler(Exception)
def exception_occurred(e):
    trace = traceback.format_tb(sys.exc_info()[2])
    app.logger.error("{0} Traceback occurred:\n".format(time.ctime()) +
                     "{0}\nTraceback completed".format("n".join(trace)))
    trace = "<br>".join(trace)
    trace.replace('\n', '<br>')
    return render_template('error.html', exception=trace,
                           debug=app.config['DEBUG'])

@app.route('/error', methods=['GET'])
def errorpage():
    if request.method == 'GET':
        return render_template('error.html')


@app.errorhandler(404)
def not_found(e):
  return render_template("404.html")


@app.errorhandler(Exception)
def handle_exception(e):
    # pass through HTTP errors
    if isinstance(e, HTTPException):
        return e
    # now you're handling non-HTTP exceptions only
    return render_template("500.html", e=e), 500


# @app.template_filter('datetimeformat')
# def datetimeformat(value, format='%m/%d/%Y, %H:%M:%S'):
#     d = datetime.strptime(value, '%Y-%b-%m %I:%M:%S.%f %Z')
#     return d.strftime(format)


@app.route('/', methods=['GET'])
def home():
    """Home page - play with it if you must!"""
    return render_template('home.html')


@app.route('/support', methods=['GET', 'POST'])
def support():
    """
    Support page, utilize mailgun to send message
    mailto:user-support@opensciencegrid.org
    """
    if request.method == 'GET':
        return render_template('support_email_form.html')
    elif request.method == 'POST':
        email = request.form['email']
        description = request.form['description']
        # mailgun setup here
        # user-support@opensciencegrid.org
        r = requests.post("https://api.mailgun.net/v3/api.ci-connect.net/messages",
                    auth=('api', mailgun_api_token),
                    data={
                        "from": "<"+email+">",
                        "to": ["fijalawa@inappmail.com"],
                        "cc": "<{}>".format(email),
                        "subject": "OSG Support Inquiry",
                        "text": description
                    })
        if r.status_code == requests.codes.ok:
            flash("Successfully sent message to the OSG support team.", 'success')
            return redirect(url_for('support'))
        else:
            flash("Unable to send message", 'warning')
            return redirect(url_for('support'))


@app.route('/users-groups', methods=['GET'])
def users_groups():
    """Groups that user's are specifically members of"""
    if request.method == 'GET':
        query = {'token': ciconnect_api_token,
                 'globus_id': session['primary_identity']}

        user = requests.get(ciconnect_api_endpoint + '/v1alpha1/find_user', params=query)
        user = user.json()
        unix_name = user['metadata']['unix_name']

        users_group_memberships = requests.get(ciconnect_api_endpoint + '/v1alpha1/users/' + unix_name + '/groups', params=query)
        users_group_memberships = users_group_memberships.json()['group_memberships']

        multiplexJson = {}
        group_membership_status = {}
        for group in users_group_memberships:
            if group['state'] not in ['nonmember']:
                group_name = group['name']
                group_query = "/v1alpha1/groups/" + group_name + "?token=" + query['token']
                multiplexJson[group_query] = {"method":"GET"}
                group_membership_status[group_query] = group['state']
        # POST request for multiplex return
        multiplex = requests.post(
            ciconnect_api_endpoint + '/v1alpha1/multiplex', params=query, json=multiplexJson)
        multiplex = multiplex.json()
        # print(multiplex)

        users_groups = []
        for group in multiplex:
            users_groups.append((json.loads(multiplex[group]['body']), group_membership_status[group]))
        # users_groups = [group for group in users_groups if len(group['name'].split('.')) == 3]

        # Query user's pending project requests
        project_requests = requests.get(ciconnect_api_endpoint + '/v1alpha1/users/' + unix_name + '/group_requests', params=query)
        project_requests = project_requests.json()['groups']
        # Check if user is active member of OSG specifically
        user_status = requests.get(ciconnect_api_endpoint + '/v1alpha1/users/' + session['unix_name'] + '/groups/root.osg', params=query)
        user_status = user_status.json()['membership']['state']

        return render_template('users_groups.html', groups=users_groups, project_requests=project_requests, user_status=user_status)

@app.route('/users-groups/pending', methods=['GET'])
def users_groups_pending():
    """Groups that user's are specifically members of"""
    if request.method == 'GET':
        query = {'token': ciconnect_api_token,
                 'globus_id': session['primary_identity']}

        user = requests.get(ciconnect_api_endpoint + '/v1alpha1/find_user', params=query)
        user = user.json()
        unix_name = user['metadata']['unix_name']

        # Query user's pending project requests
        project_requests = requests.get(ciconnect_api_endpoint + '/v1alpha1/users/' + unix_name + '/group_requests', params=query)
        project_requests = project_requests.json()['groups']
        # Check if user is active member of OSG specifically
        user_status = requests.get(ciconnect_api_endpoint + '/v1alpha1/users/' + session['unix_name'] + '/groups/root.osg', params=query)
        user_status = user_status.json()['membership']['state']
        return render_template('users_groups_pending.html', project_requests=project_requests, user_status=user_status)


@app.route('/groups', methods=['GET'])
def groups():
    """OSG Connect groups"""
    if request.method == 'GET':
        query = {'token': session['access_token']}
        # Query to list subgroups or projects within OSG specifcally
        osg_groups = requests.get(ciconnect_api_endpoint + '/v1alpha1/groups/root.osg/subgroups', params=query)
        # print(osg_groups)
        osg_groups = osg_groups.json()['groups']
        osg_groups = [group for group in osg_groups if len(group['name'].split('.')) == 3]

        # Check if user is active member of OSG specifically
        user_status = requests.get(ciconnect_api_endpoint + '/v1alpha1/users/' + session['unix_name'] + '/groups/root.osg', params=query)
        user_status = user_status.json()['membership']['state']

        return render_template('groups.html', groups=osg_groups, user_status=user_status)


@app.route('/groups/new', methods=['GET', 'POST'])
@authenticated
def create_group():
    """Create groups"""
    query = {'token': session['access_token']}
    if request.method == 'GET':
        sciences = requests.get(ciconnect_api_endpoint + '/v1alpha1/fields_of_science')
        sciences = sciences.json()['fields_of_science']
        return render_template('groups_create.html', sciences=sciences)
    elif request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        field_of_science = request.form['field_of_science']
        description = request.form['description']

        put_group = {"apiVersion": 'v1alpha1', "kind": "Group",
                        'metadata': {'name': name,
                                    'field_of_science': field_of_science,
                                    'email': email, 'phone': phone,
                                    'description': description}}
        create_group = requests.put(ciconnect_api_endpoint + '/v1alpha1/groups/root/subgroups/' + name, params=query, json=put_group)
        if create_group.status_code == requests.codes.ok:
            flash("Successfully created group", 'success')
            return redirect(url_for('groups'))
        else:
            err_message = create_group.json()['message']
            flash('Failed to create group: {}'.format(err_message), 'warning')
            return redirect(url_for('groups'))


@app.route('/groups/<group_name>', methods=['GET', 'POST'])
@authenticated
def view_group(group_name):
    """Detailed view of specific groups"""
    query = {'token': ciconnect_api_token,
             'globus_id': session['primary_identity']}

    user = requests.get(ciconnect_api_endpoint + '/v1alpha1/find_user', params=query)
    user = user.json()
    unix_name = user['metadata']['unix_name']

    if request.method == 'GET':
        group = requests.get(ciconnect_api_endpoint + '/v1alpha1/groups/'
                            + group_name, params=query)
        group = group.json()['metadata']
        group_creation_date = group['creation_date'].split(' ')[0]
        # print(group_creation_date)
        # Get User's Group Status
        user_status = requests.get(
                        ciconnect_api_endpoint + '/v1alpha1/groups/' +
                        group_name + '/members/' + unix_name, params=query)
        user_status = user_status.json()['membership']['state']

        # Query to return user's membership status in a group, specifically if user is OSG admin
        r = requests.get(
            ciconnect_api_endpoint + '/v1alpha1/users/' + unix_name + '/groups/root.osg', params=query)
        osg_status = r.json()['membership']['state']

        pi_info = {}

        try:
            additional_attributes = requests.get(ciconnect_api_endpoint + '/v1alpha1/groups/'
                                            + group_name + '/attributes/OSG:PI_Name', params=query)
            PI_Name = additional_attributes.json()['data']
            pi_info['PI_Name'] = PI_Name
        except:
            PI_Name = None
            pi_info['PI_Name'] = PI_Name

        try:
            additional_attributes = requests.get(ciconnect_api_endpoint + '/v1alpha1/groups/'
                                            + group_name + '/attributes/OSG:PI_Email', params=query)
            PI_Email = additional_attributes.json()['data']
            pi_info['PI_Email'] = PI_Email
        except:
            PI_Email = None
            pi_info['PI_Email'] = PI_Email

        try:
            additional_attributes = requests.get(ciconnect_api_endpoint + '/v1alpha1/groups/'
                                            + group_name + '/attributes/OSG:PI_Organization', params=query)
            PI_Organization = additional_attributes.json()['data']
            pi_info['PI_Organization'] = PI_Organization
        except:
            PI_Organization = None
            pi_info['PI_Organization'] = PI_Organization

        return render_template('group_profile.html', group=group,
                                group_name=group_name, user_status=user_status,
                                pi_info=pi_info, osg_status=osg_status,
                                group_creation_date=group_creation_date)
    elif request.method == 'POST':
        '''Request membership to join group'''
        put_query = {"apiVersion": 'v1alpha1',
                        'group_membership': {'state': 'pending'}}
        user_status = requests.put(
                        ciconnect_api_endpoint + '/v1alpha1/groups/' +
                        group_name + '/members/' + unix_name, params=query, json=put_query)
        # print("UPDATED MEMBERSHIP: {}".format(user_status))
        return redirect(url_for('view_group', group_name=group_name))


@app.route('/groups-xhr/<group_name>', methods=['GET'])
@authenticated
def view_group_ajax(group_name):
    group, user_status = view_group_ajax_request(group_name)
    return jsonify(group, user_status)

def view_group_ajax_request(group_name):
    query = {'token': ciconnect_api_token,
             'globus_id': session['primary_identity']}

    user = requests.get(ciconnect_api_endpoint + '/v1alpha1/find_user', params=query)
    user = user.json()
    unix_name = user['metadata']['unix_name']

    group = requests.get(ciconnect_api_endpoint + '/v1alpha1/groups/' + group_name, params=query)
    group = group.json()['metadata']
    group_name = group['name']
    # Get User's Group Status
    user_status = requests.get(
                    ciconnect_api_endpoint + '/v1alpha1/groups/' +
                    group_name + '/members/' + unix_name, params=query)
    user_status = user_status.json()['membership']['state']

    return group, user_status


@app.route('/groups/<group_name>/delete', methods=['POST'])
@authenticated
def delete_group(group_name):
    if request.method == 'POST':
        token_query = {'token': session['access_token']}

        r = requests.delete(
            ciconnect_api_endpoint + '/v1alpha1/groups/' + group_name, params=token_query)
        print(r)

        if r.status_code == requests.codes.ok:
            flash("Successfully deleted group", 'success')
            return redirect(url_for('groups'))
        else:
            err_message = r.json()['message']
            flash('Failed to delete group: {}'.format(err_message), 'warning')
            return redirect(url_for('view_group', group_name=group_name))


@app.route('/groups/<group_name>/members', methods=['GET', 'POST'])
@authenticated
def view_group_members(group_name):
    """Detailed view of group's members"""
    query = {'token': ciconnect_api_token}
    if request.method == 'GET':
        # Get group information
        group = requests.get(ciconnect_api_endpoint + '/v1alpha1/groups/'
                            + group_name, params=query)
        group = group.json()['metadata']

        # Get User's Group Status
        user_status = requests.get(
                        ciconnect_api_endpoint + '/v1alpha1/groups/' +
                        group_name + '/members/' + session['unix_name'], params=query)
        user_status = user_status.json()['membership']['state']

        # Query to return user's membership status in a group, specifically if user is OSG admin
        r = requests.get(
            ciconnect_api_endpoint + '/v1alpha1/users/' + session['unix_name'] + '/groups/root.osg', params=query)
        osg_status = r.json()['membership']['state']

        return render_template('group_profile_members.html', group_name=group_name,
                                user_status=user_status, group=group, osg_status=osg_status)


@app.route('/groups-xhr/<group_name>/members', methods=['GET'])
@authenticated
def view_group_members_ajax(group_name):
    user_dict, users_statuses = view_group_members_ajax_request(group_name)
    return jsonify(user_dict, users_statuses)

def view_group_members_ajax_request(group_name):
    """Detailed view of group's members"""
    query = {'token': ciconnect_api_token}
    if request.method == 'GET':
        group_members = requests.get(ciconnect_api_endpoint + '/v1alpha1/groups/' + group_name + '/members', params=query)
        # print(group_members.json())
        memberships = group_members.json()['memberships']
        multiplexJson = {}
        users_statuses = {}

        # start = time.time()
        # print("START")

        for user in memberships:
            unix_name = user['user_name']
            user_state = user['state']
            if (user_state != 'nonmember' and unix_name != 'root'):
                user_query = "/v1alpha1/users/" + unix_name + "?token=" + query['token']
                multiplexJson[user_query] = {"method":"GET"}
                users_statuses[unix_name] = user_state
        # POST request for multiplex return
        multiplex = requests.post(
            ciconnect_api_endpoint + '/v1alpha1/multiplex', params=query, json=multiplexJson)
        multiplex = multiplex.json()
        user_dict = {}
        group_user_dict = {}

        # end = time.time()
        # print(end - start)

        for user in multiplex:
            user_name = user.split('/')[3].split('?')[0]
            user_dict[user_name] = json.loads(multiplex[user]['body'])

        for user, info in user_dict.items():
            for group_membership in info['metadata']['group_memberships']:
                if group_membership['name'] == group_name:
                    group_user_dict[user] = info

        # Get User's Group Status
        user_status = requests.get(
                        ciconnect_api_endpoint + '/v1alpha1/groups/' +
                        group_name + '/members/' + session['unix_name'], params=query)
        user_status = user_status.json()['membership']['state']
        query = {'token': ciconnect_api_token}
        user_super = requests.get(
                        ciconnect_api_endpoint + '/v1alpha1/users/' + session['unix_name'], params=query)
        try:
            user_super = user_super.json()['metadata']['superuser']
        except:
            user_super = False

        return user_dict, users_statuses


@app.route('/groups-pending-members-count-xhr/<group_name>/members', methods=['GET'])
@authenticated
def group_pending_members_count_ajax(group_name):
    pending_user_count = group_pending_members_count_request(group_name)
    return jsonify(pending_user_count)

def group_pending_members_count_request(group_name):
    """Get a group's pending members count"""
    query = {'token': ciconnect_api_token}
    if request.method == 'GET':
        group_members = requests.get(ciconnect_api_endpoint + '/v1alpha1/groups/' + group_name + '/members', params=query)
        # print(group_members.json())
        memberships = group_members.json()['memberships']
        pending_user_count = 0

        for user in memberships:
            if user['state'] == 'pending':
                pending_user_count += 1

        return pending_user_count



@app.route('/groups/<group_name>/members-requests', methods=['GET', 'POST'])
@authenticated
def view_group_members_requests(group_name):
    """Detailed view of group's pending members"""
    query = {'token': ciconnect_api_token}
    if request.method == 'GET':
        # Get group information
        group = requests.get(ciconnect_api_endpoint + '/v1alpha1/groups/'
                            + group_name, params=query)
        group = group.json()['metadata']

        display_name = '-'.join(group_name.split('.')[1:])
        group_members = requests.get(ciconnect_api_endpoint + '/v1alpha1/groups/' + group_name + '/members', params=query)
        memberships = group_members.json()['memberships']
        multiplexJson = {}
        users_statuses = {}

        for user in memberships:
            unix_name = user['user_name']
            if user['state'] == 'pending':
                user_state = user['state']
                user_query = "/v1alpha1/users/" + unix_name + "?token=" + query['token']
                multiplexJson[user_query] = {"method":"GET"}
                users_statuses[unix_name] = user_state

        # POST request for multiplex return
        multiplex = requests.post(
            ciconnect_api_endpoint + '/v1alpha1/multiplex', params=query, json=multiplexJson)
        multiplex = multiplex.json()
        user_dict = {}
        for user in multiplex:
            user_name = user.split('/')[3].split('?')[0]
            user_dict[user_name] = json.loads(multiplex[user]['body'])

        # Get User's Group Status
        user_status = requests.get(
                        ciconnect_api_endpoint + '/v1alpha1/groups/' +
                        group_name + '/members/' + session['unix_name'], params=query)
        user_status = user_status.json()['membership']['state']
        query = {'token': ciconnect_api_token}
        user_super = requests.get(
                        ciconnect_api_endpoint + '/v1alpha1/users/' + session['unix_name'], params=query)
        try:
            user_super = user_super.json()['metadata']['superuser']
        except:
            user_super = False

        # Query to return user's membership status in a group, specifically if user is OSG admin
        r = requests.get(
            ciconnect_api_endpoint + '/v1alpha1/users/' + session['unix_name'] + '/groups/root.osg', params=query)
        osg_status = r.json()['membership']['state']

        return render_template('group_profile_members_requests.html',
                                group_members=user_dict, group_name=group_name,
                                display_name=display_name, user_status=user_status,
                                user_super=user_super,
                                users_statuses=users_statuses, group=group,
                                osg_status=osg_status)


@app.route('/groups/<group_name>/add_members', methods=['GET', 'POST'])
@authenticated
def view_group_add_members(group_name):
    """Detailed view of group's non-members"""
    query = {'token': ciconnect_api_token}
    if request.method == 'GET':
        # # Get root base group users
        # enclosing_group_name = '.'.join(group_name.split('.')[:-1])
        # # print(enclosing_group_name)
        # enclosing_group = requests.get(ciconnect_api_endpoint + '/v1alpha1/groups/'
        #                     + enclosing_group_name + '/members', params=query)
        # enclosing_group = enclosing_group.json()['memberships']
        # enclosing_group_members_names = [member['user_name'] for member in enclosing_group]
        # # print(base_group)
        #
        # Get group information
        group = requests.get(ciconnect_api_endpoint + '/v1alpha1/groups/'
                            + group_name, params=query)
        group = group.json()['metadata']

        display_name = '-'.join(group_name.split('.')[1:])
        # group_members = requests.get(ciconnect_api_endpoint + '/v1alpha1/groups/' + group_name + '/members', params=query)
        # memberships = group_members.json()['memberships']
        # memberships_names = [member['user_name'] for member in memberships]
        #
        # non_members = list(set(enclosing_group_members_names) - set(memberships_names))
        #
        # multiplexJson = {}
        #
        # for user in non_members:
        #     unix_name = user
        #     user_query = "/v1alpha1/users/" + unix_name + "?token=" + query['token']
        #     multiplexJson[user_query] = {"method":"GET"}
        #
        # # POST request for multiplex return
        # multiplex = requests.post(
        #     ciconnect_api_endpoint + '/v1alpha1/multiplex', params=query, json=multiplexJson)
        # multiplex = multiplex.json()
        # user_dict = {}
        # for user in multiplex:
        #     user_name = user.split('/')[3].split('?')[0]
        #     user_dict[user_name] = json.loads(multiplex[user]['body'])

        # Get User's Group Status
        user_status = requests.get(
                        ciconnect_api_endpoint + '/v1alpha1/groups/' +
                        group_name + '/members/' + session['unix_name'], params=query)
        user_status = user_status.json()['membership']['state']
        query = {'token': ciconnect_api_token}
        user_super = requests.get(
                        ciconnect_api_endpoint + '/v1alpha1/users/' + session['unix_name'], params=query)
        try:
            user_super = user_super.json()['metadata']['superuser']
        except:
            user_super = False

        # Query to return user's membership status in a group, specifically if user is OSG admin
        r = requests.get(
            ciconnect_api_endpoint + '/v1alpha1/users/' + session['unix_name'] + '/groups/root.osg', params=query)
        osg_status = r.json()['membership']['state']

        return render_template('group_profile_add_members.html', group_name=group_name,
                                display_name=display_name, user_status=user_status,
                                user_super=user_super, group=group, osg_status=osg_status)


@app.route('/groups-xhr/<group_name>/add_members', methods=['GET', 'POST'])
@authenticated
def view_group_add_members_xhr(group_name):
    """Detailed view of group's 'add members' page"""
    non_members = view_group_add_members_request(group_name)
    return jsonify(non_members)

def view_group_add_members_request(group_name):
    """Detailed view of group's non-members"""
    query = {'token': ciconnect_api_token}
    if request.method == 'GET':
        # Get root base group users
        # if 'login-nodes' in group_name:
        #     enclosing_group_name = 'root.osg'
        # else:
        enclosing_group_name = '.'.join(group_name.split('.')[:-1])

        enclosing_group = requests.get(ciconnect_api_endpoint + '/v1alpha1/groups/'
                            + enclosing_group_name + '/members', params=query)
        enclosing_group = enclosing_group.json()['memberships']
        enclosing_group_members_names = [member['user_name'] for member in enclosing_group]
        # print(base_group)

        # Get group information
        group = requests.get(ciconnect_api_endpoint + '/v1alpha1/groups/'
                            + group_name, params=query)
        group = group.json()['metadata']

        display_name = '-'.join(group_name.split('.')[1:])
        group_members = requests.get(ciconnect_api_endpoint + '/v1alpha1/groups/' + group_name + '/members', params=query)
        memberships = group_members.json()['memberships']
        memberships_names = [member['user_name'] for member in memberships]

        non_members = list(set(enclosing_group_members_names) - set(memberships_names))

        multiplexJson = {}

        for user in non_members:
            unix_name = user
            user_query = "/v1alpha1/users/" + unix_name + "?token=" + query['token']
            multiplexJson[user_query] = {"method":"GET"}

        # POST request for multiplex return
        multiplex = requests.post(
            ciconnect_api_endpoint + '/v1alpha1/multiplex', params=query, json=multiplexJson)
        multiplex = multiplex.json()
        user_dict = {}
        for user in multiplex:
            user_name = user.split('/')[3].split('?')[0]
            user_dict[user_name] = json.loads(multiplex[user]['body'])

        # Get User's Group Status
        user_status = requests.get(
                        ciconnect_api_endpoint + '/v1alpha1/groups/' +
                        group_name + '/members/' + session['unix_name'], params=query)
        user_status = user_status.json()['membership']['state']
        query = {'token': ciconnect_api_token}
        user_super = requests.get(
                        ciconnect_api_endpoint + '/v1alpha1/users/' + session['unix_name'], params=query)
        try:
            user_super = user_super.json()['metadata']['superuser']
        except:
            user_super = False

        # Query to return user's membership status in a group, specifically if user is OSG admin
        r = requests.get(
            ciconnect_api_endpoint + '/v1alpha1/users/' + session['unix_name'] + '/groups/root.osg', params=query)
        osg_status = r.json()['membership']['state']

        return user_dict



@app.route('/groups/<group_name>/add_group_member/<unix_name>', methods=['POST'])
@authenticated
def add_group_member(group_name, unix_name):
    if request.method == 'POST':
        query = {'token': session['access_token']}

        put_query = {"apiVersion": 'v1alpha1',
                        'group_membership': {'state': 'active'}}
        user_status = requests.put(
                        ciconnect_api_endpoint + '/v1alpha1/groups/' +
                        group_name + '/members/' + unix_name, params=query, json=put_query)
        # print("UPDATED MEMBERSHIP: {}".format(user_status))

        if user_status.status_code == requests.codes.ok:
            flash("Successfully added member to group", 'success')
            return redirect(url_for('view_group_members', group_name=group_name))
        else:
            err_message = user_status.json()['message']
            flash('Failed to add member to group: {}'.format(err_message), 'warning')
            return redirect(url_for('view_group_members', group_name=group_name))


@app.route('/groups/<group_name>/delete_group_member/<unix_name>', methods=['POST'])
@authenticated
def remove_group_member(group_name, unix_name):
    if request.method == 'POST':
        query = {'token': session['access_token']}
        try:
            message = request.form['denial-message']
            denial_message = {'message': message}
            remove_user = requests.delete(
                            ciconnect_api_endpoint + '/v1alpha1/groups/' +
                            group_name + '/members/' + unix_name, params=query, json=denial_message)
        except:
            remove_user = requests.delete(
                            ciconnect_api_endpoint + '/v1alpha1/groups/' +
                            group_name + '/members/' + unix_name, params=query)
        # print("UPDATED remove_user: {}".format(remove_user))

        if remove_user.status_code == requests.codes.ok:
            flash("Successfully removed member from group", 'success')
            return redirect(url_for('view_group_members', group_name=group_name))
        else:
            err_message = remove_user.json()['message']
            flash('Failed to remove member from group: {}'.format(err_message), 'warning')
            return redirect(url_for('view_group_members', group_name=group_name))


@app.route('/groups/<group_name>/admin_group_member/<unix_name>', methods=['POST'])
@authenticated
def admin_group_member(group_name, unix_name):
    if request.method == 'POST':
        query = {'token': session['access_token']}

        put_query = {"apiVersion": 'v1alpha1',
                        'group_membership': {'state': 'admin'}}
        user_status = requests.put(
                        ciconnect_api_endpoint + '/v1alpha1/groups/' +
                        group_name + '/members/' + unix_name, params=query, json=put_query)
        # print("UPDATED MEMBERSHIP: {}".format(user_status))

        if user_status.status_code == requests.codes.ok:
            flash("Successfully updated member to admin", 'success')
            return redirect(url_for('view_group_members', group_name=group_name))
        else:
            err_message = user_status.json()['message']
            flash('Failed make member an admin: {}'.format(err_message), 'warning')
            return redirect(url_for('view_group_members', group_name=group_name))


@app.route('/groups/<group_name>/subgroups', methods=['GET', 'POST'])
@authenticated
def view_group_subgroups(group_name):
    """Detailed view of group's subgroups"""
    query = {'token': ciconnect_api_token}
    if request.method == 'GET':
        # Get group information
        group = requests.get(ciconnect_api_endpoint + '/v1alpha1/groups/'
                            + group_name, params=query)
        group = group.json()['metadata']
        # Get User's Group Status
        user_status = requests.get(
                        ciconnect_api_endpoint + '/v1alpha1/groups/' +
                        group_name + '/members/' + session['unix_name'], params=query)

        user_status = user_status.json()['membership']['state']

        # Check if user is active member of OSG specifically
        osg_status = requests.get(ciconnect_api_endpoint + '/v1alpha1/users/' + session['unix_name'] + '/groups/root.osg', params=query)
        osg_status = osg_status.json()['membership']['state']

        return render_template('group_profile_subgroups.html', group_name=group_name,
                                user_status=user_status, group=group, osg_status=osg_status)

@app.route('/groups-xhr/<group_name>/subgroups', methods=['GET', 'POST'])
@authenticated
def view_group_subgroups_xhr(group_name):
    """Detailed view of group's subgroups"""
    subgroups = view_group_subgroups_request(group_name)
    return jsonify(subgroups)

def view_group_subgroups_request(group_name):
    query = {'token': ciconnect_api_token}
    if request.method == 'GET':
        # Get group's subgroups information
        subgroups = requests.get(ciconnect_api_endpoint + '/v1alpha1/groups/' + group_name + '/subgroups', params=query)
        subgroups = subgroups.json()['groups']
        subgroups = [subgroup for subgroup in subgroups if (len(subgroup['name'].split('.')) == 3 and not subgroup['pending'])]

        return subgroups


@app.route('/groups/<group_name>/subgroups-requests', methods=['GET', 'POST'])
@authenticated
def view_group_subgroups_requests(group_name):
    """List view of group's subgroups requests"""
    query = {'token': ciconnect_api_token}
    if request.method == 'GET':
        # Get group information
        group = requests.get(ciconnect_api_endpoint + '/v1alpha1/groups/'
                            + group_name, params=query)
        group = group.json()['metadata']

        display_name = '-'.join(group_name.split('.')[1:])
        # subgroups = requests.get(ciconnect_api_endpoint + '/v1alpha1/groups/' + group_name + '/subgroups', params=query)
        # subgroups = subgroups.json()['groups']
        # Get User's Group Status
        user_status = requests.get(
                        ciconnect_api_endpoint + '/v1alpha1/groups/' +
                        group_name + '/members/' + session['unix_name'], params=query)

        user_status = user_status.json()['membership']['state']

        subgroup_requests = requests.get(ciconnect_api_endpoint + '/v1alpha1/groups/' + group_name + '/subgroup_requests', params=query)
        subgroup_requests = subgroup_requests.json()['groups']

        return render_template('group_profile_subgroups_requests.html',
                                display_name=display_name, subgroup_requests=subgroup_requests,
                                group_name=group_name, user_status=user_status,
                                group=group)


@app.route('/groups-xhr/<group_name>/subgroups-requests', methods=['GET', 'POST'])
@authenticated
def view_group_subgroups_ajax(group_name):
    subgroup_requests = view_group_subgroups_ajax_requests(group_name)
    subgroup_requests_count = len(subgroup_requests)
    return jsonify(subgroup_requests, subgroup_requests_count)

def view_group_subgroups_ajax_requests(group_name):
    """List view of group's subgroups requests"""
    query = {'token': ciconnect_api_token}
    if request.method == 'GET':
        # display_name = '-'.join(group_name.split('.')[1:])
        # # subgroups = requests.get(ciconnect_api_endpoint + '/v1alpha1/groups/' + group_name + '/subgroups', params=query)
        # # subgroups = subgroups.json()['groups']
        # # Get User's Group Status
        # user_status = requests.get(
        #                 ciconnect_api_endpoint + '/v1alpha1/groups/' +
        #                 group_name + '/members/' + session['unix_name'], params=query)
        #
        # user_status = user_status.json()['membership']['state']

        subgroup_requests = requests.get(ciconnect_api_endpoint + '/v1alpha1/groups/' + group_name + '/subgroup_requests', params=query)
        subgroup_requests = subgroup_requests.json()['groups']

        return subgroup_requests


@app.route('/groups/<group_name>/subgroups/new', methods=['GET', 'POST'])
@authenticated
def create_subgroup(group_name):
    token_query = {'token': session['access_token']}
    if request.method == 'GET':
        sciences = requests.get(ciconnect_api_endpoint + '/v1alpha1/fields_of_science')
        sciences = sciences.json()['fields_of_science']
        group_members = requests.get(ciconnect_api_endpoint + '/v1alpha1/groups/' + group_name + '/members', params=token_query)
        try:
            group_members = group_members.json()['memberships']
            group_admins = [member for member in group_members if member['state'] == 'admin']
        except:
            group_admins = []
        # Check if user is active member of OSG specifically
        user_status = requests.get(ciconnect_api_endpoint + '/v1alpha1/users/' + session['unix_name'] + '/groups/root.osg', params=token_query)
        user_status = user_status.json()['membership']['state']

        # Get enclosing group information
        group = requests.get(ciconnect_api_endpoint + '/v1alpha1/groups/' + group_name, params=token_query)
        group = group.json()['metadata']
        return render_template('groups_create.html', sciences=sciences, group_name=group_name, group_admins=group_admins, user_status=user_status, group=group)

    elif request.method == 'POST':
        name = request.form['name']
        display_name = request.form['display-name']
        email = request.form['email']
        phone = request.form['phone']
        field_of_science = request.form['field_of_science']
        description = request.form['description']

        additional_metadata = {}
        pi_name = request.form['pi-name']
        pi_email = request.form['pi-email']
        pi_organization = request.form['pi-org']

        if pi_name:
            additional_metadata['OSG:PI_Name'] = pi_name
        if pi_email:
            additional_metadata['OSG:PI_Email'] = pi_email
        if pi_organization:
            additional_metadata['OSG:PI_Organization'] = pi_organization

        if len(additional_metadata) > 0:
            put_query = {"apiVersion": 'v1alpha1',
                            'metadata': {'name': name,
                                        'display_name': display_name,
                                        'purpose': field_of_science,
                                        'email': email, 'phone': phone,
                                        'description': description,
                                        'additional_attributes': additional_metadata}}
        else:
            put_query = {"apiVersion": 'v1alpha1',
                            'metadata': {'name': name, 'display_name': display_name,
                                        'purpose': field_of_science,
                                        'email': email, 'phone': phone,
                                        'description': description}}
        # print(put_query)

        r = requests.put(
            ciconnect_api_endpoint + '/v1alpha1/groups/' + group_name +
            '/subgroup_requests/' + name, params=token_query, json=put_query)
        full_created_group_name = group_name + '.' + name

        # Check if user is active member of OSG specifically
        user_status = requests.get(ciconnect_api_endpoint + '/v1alpha1/users/' + session['unix_name'] + '/groups/root.osg', params=token_query)
        user_status = user_status.json()['membership']['state']

        if r.status_code == requests.codes.ok:
            if user_status == 'admin':
                flash("Successfully created project.", 'success')
                return redirect(url_for('view_group', group_name=full_created_group_name))
            else:
                flash("The OSG support team has been notified of your requested project.", 'success')
                return redirect(url_for('users_groups_pending'))
        else:
            err_message = r.json()['message']
            flash('Failed to request project creation: {}'.format(err_message), 'warning')
            return redirect(url_for('view_group_subgroups_requests', group_name=group_name))


@app.route('/groups/<group_name>/requests/edit', methods=['GET', 'POST'])
@authenticated
def edit_subgroup_requests(group_name):
    token_query = {'token': session['access_token']}
    enclosing_group_name = '.'.join(group_name.split('.')[:-1])
    if request.method == 'GET':
        sciences = requests.get(ciconnect_api_endpoint + '/v1alpha1/fields_of_science')
        sciences = sciences.json()['fields_of_science']
        group = requests.get(ciconnect_api_endpoint + '/v1alpha1/groups/' + group_name, params=token_query)
        group = group.json()['metadata']

        subgroup_requests = requests.get(ciconnect_api_endpoint + '/v1alpha1/groups/' + enclosing_group_name + '/subgroup_requests', params=token_query)
        subgroup_requests = subgroup_requests.json()['groups']
        pi_info = {}

        for subgroup_request in subgroup_requests:
            if subgroup_request['name'] == group_name:
                pi_info['PI_Name'] = subgroup_request['additional_attributes']['OSG:PI_Name']
                pi_info['PI_Email'] = subgroup_request['additional_attributes']['OSG:PI_Email']
                pi_info['PI_Organization'] = subgroup_request['additional_attributes']['OSG:PI_Organization']

        return render_template('groups_requests_edit.html', sciences=sciences, group_name=group_name, group=group, pi_info=pi_info)

    elif request.method == 'POST':
        name = request.form['name']
        display_name = request.form['display-name']
        email = request.form['email']
        phone = request.form['phone']
        field_of_science = request.form['field_of_science']
        description = request.form['description']

        additional_metadata = {}
        pi_name = request.form['pi-name']
        pi_email = request.form['pi-email']
        pi_organization = request.form['pi-org']

        if pi_name:
            additional_metadata['OSG:PI_Name'] = pi_name
        if pi_email:
            additional_metadata['OSG:PI_Email'] = pi_email
        if pi_organization:
            additional_metadata['OSG:PI_Organization'] = pi_organization

        new_unix_name = enclosing_group_name + '.' + name

        if new_unix_name == group_name:
            put_query = {"apiVersion": 'v1alpha1',
                            'metadata': {'display_name': display_name,
                                        'purpose': field_of_science,
                                        'email': email, 'phone': phone,
                                        'description': description,
                                        'additional_attributes': additional_metadata}}
        else:
            put_query = {"apiVersion": 'v1alpha1',
                            'metadata': {'name': name,
                                        'display_name': display_name,
                                        'purpose': field_of_science,
                                        'email': email, 'phone': phone,
                                        'description': description,
                                        'additional_attributes': additional_metadata}}
        # print(put_query)

        r = requests.put(
            ciconnect_api_endpoint + '/v1alpha1/groups/' + group_name, params=token_query, json=put_query)

        enclosing_group_name = '.'.join(group_name.split('.')[:-1])
        if r.status_code == requests.codes.ok:
            flash("The OSG support team has been notified of your updated project request.", 'success')
            return redirect(url_for('users_groups_pending'))
        else:
            err_message = r.json()['message']
            flash('Failed to edit project request: {}'.format(err_message), 'warning')
            return redirect(url_for('edit_subgroup', group_name=group_name))


@app.route('/groups/<group_name>/edit', methods=['GET', 'POST'])
@authenticated
def edit_subgroup(group_name):
    token_query = {'token': session['access_token']}
    if request.method == 'GET':
        sciences = requests.get(ciconnect_api_endpoint + '/v1alpha1/fields_of_science')
        sciences = sciences.json()['fields_of_science']
        group = requests.get(ciconnect_api_endpoint + '/v1alpha1/groups/' + group_name, params=token_query)
        group = group.json()['metadata']

        pi_info = {}

        try:
            additional_attributes = requests.get(ciconnect_api_endpoint + '/v1alpha1/groups/'
                                            + group_name + '/attributes/OSG:PI_Name', params=query)
            PI_Name = additional_attributes.json()['data']
            pi_info['PI_Name'] = PI_Name
        except:
            PI_Name = None
            pi_info['PI_Name'] = PI_Name

        try:
            additional_attributes = requests.get(ciconnect_api_endpoint + '/v1alpha1/groups/'
                                            + group_name + '/attributes/OSG:PI_Email', params=query)
            PI_Email = additional_attributes.json()['data']
            pi_info['PI_Email'] = PI_Email
        except:
            PI_Email = None
            pi_info['PI_Email'] = PI_Email

        try:
            additional_attributes = requests.get(ciconnect_api_endpoint + '/v1alpha1/groups/'
                                            + group_name + '/attributes/OSG:PI_Organization', params=query)
            PI_Organization = additional_attributes.json()['data']
            pi_info['PI_Organization'] = PI_Organization
        except:
            PI_Organization = None
            pi_info['PI_Organization'] = PI_Organization

        print(pi_info)

        return render_template('groups_edit.html', sciences=sciences, group_name=group_name, group=group)

    elif request.method == 'POST':
        display_name = request.form['display-name']
        email = request.form['email']
        phone = request.form['phone']
        field_of_science = request.form['field_of_science']
        description = request.form['description']

        additional_metadata = {}
        pi_name = request.form['pi-name']
        pi_email = request.form['pi-email']
        pi_organization = request.form['pi-org']

        if pi_name:
            additional_metadata['OSG:PI_Name'] = pi_name
        if pi_email:
            additional_metadata['OSG:PI_Email'] = pi_email
        if pi_organization:
            additional_metadata['OSG:PI_Organization'] = pi_organization

        if len(additional_metadata) > 0:
            put_query = {"apiVersion": 'v1alpha1',
                            'metadata': {'display_name': display_name,
                                        'purpose': field_of_science,
                                        'email': email, 'phone': phone,
                                        'description': description,
                                        'additional_attributes': additional_metadata}}
        else:
            put_query = {"apiVersion": 'v1alpha1',
                            'metadata': {'display_name': display_name,
                                        'purpose': field_of_science,
                                        'email': email, 'phone': phone,
                                        'description': description}}
        print(put_query)

        r = requests.put(
            ciconnect_api_endpoint + '/v1alpha1/groups/' + group_name, params=token_query, json=put_query)
        # print(r)
        enclosing_group_name = '.'.join(group_name.split('.')[:-1])
        # print(enclosing_group_name)
        if r.status_code == requests.codes.ok:
            flash("Successfully updated project information.", 'success')
            return redirect(url_for('view_group', group_name=group_name))
        else:
            err_message = r.json()['message']
            flash('Failed to update project information: {}'.format(err_message), 'warning')
            return redirect(url_for('edit_subgroup', group_name=group_name))


@app.route('/groups/<group_name>/subgroups/<subgroup_name>/approve', methods=['GET'])
@authenticated
def approve_subgroup(group_name, subgroup_name):
    token_query = {'token': session['access_token']}
    if request.method == 'GET':
        print("GROUP NAME: {}".format(group_name))
        print("SUBGROUP NAME: {}".format(subgroup_name))

        r = requests.put(
            ciconnect_api_endpoint + '/v1alpha1/groups/' + group_name +
            '/subgroup_requests/' + subgroup_name + '/approve', params=token_query)

        if r.status_code == requests.codes.ok:
            flash("Successfully approved project creation", 'success')
            print(r.content)
            return redirect(url_for('view_group_subgroups_requests', group_name=group_name))
        else:
            err_message = r.json()['message']
            flash('Failed to approve project creation: {}'.format(err_message), 'warning')
            return redirect(url_for('view_group_subgroups_requests', group_name=group_name))


@app.route('/groups/<group_name>/subgroups/<subgroup_name>/deny', methods=['POST'])
@authenticated
def deny_subgroup(group_name, subgroup_name):
    token_query = {'token': session['access_token']}
    if request.method == 'POST':
        message = request.form['denial-message']
        denial_message = {'message': message}

        r = requests.delete(
            ciconnect_api_endpoint + '/v1alpha1/groups/' + group_name +
            '/subgroup_requests/' + subgroup_name, params=token_query, json=denial_message)

        if r.status_code == requests.codes.ok:
            flash("Denied Project Request", 'success')
            print(r.content)
            return redirect(url_for('view_group_subgroups_requests', group_name=group_name))
        else:
            err_message = r.json()['message']
            flash('Failed to deny project request: {}'.format(err_message), 'warning')
            return redirect(url_for('view_group_subgroups_requests', group_name=group_name))

################################################################################
######################### LOGIN-NODE ROUTES ####################################
################################################################################

@app.route('/login-nodes', methods=['GET'])
@authenticated
def view_login_nodes():
    """Detailed view of Login Nodes specifically for OSG"""
    query = {'token': ciconnect_api_token,
             'globus_id': session['primary_identity']}

    if request.method == 'GET':
        # Check if user is Admin of OSG
        user = requests.get(ciconnect_api_endpoint + '/v1alpha1/find_user', params=query)
        user = user.json()
        unix_name = user['metadata']['unix_name']

        group = requests.get(ciconnect_api_endpoint + '/v1alpha1/groups/'
                            + 'root.osg.login-nodes', params=query)
        group = group.json()['metadata']

        current_time = datetime.datetime.now()
        previous_time_unix = int((current_time - datetime.timedelta(hours=5)).strftime("%s"))
        current_time_unix = current_time.strftime("%s")

        login02_load_grafana = 'https://grafana.mwt2.org/d-solo/JiH0SAoZk/connect-servers?orgId=1&from=now-3h&to=now&var-Server=login02_osgconnect_net&panelId=7'
        login02_jobs_grafana = 'https://grafana.mwt2.org/d-solo/JiH0SAoZk/connect-servers?orgId=1&from=now-3h&to=now&var-Server=login02_osgconnect_net&panelId=9'

        login03_load_grafana = 'https://grafana.mwt2.org/d-solo/JiH0SAoZk/connect-servers?orgId=1&from=now-3h&to=now&var-Server=login03_osgconnect_net&panelId=7'
        login03_jobs_grafana = 'https://grafana.mwt2.org/d-solo/JiH0SAoZk/connect-servers?orgId=1&from=now-3h&to=now&var-Server=login03_osgconnect_net&panelId=9'

        login_test_load_grafana = 'https://grafana.mwt2.org/d-solo/JiH0SAoZk/connect-servers?orgId=1&from=now-3h&to=now&var-Server=test_osgconnect_net&panelId=7'
        login_test_jobs_grafana = 'https://grafana.mwt2.org/d-solo/JiH0SAoZk/connect-servers?orgId=1&from=now-3h&to=now&var-Server=test_osgconnect_net&panelId=9'

        return render_template('login_nodes.html', group=group,
                                login02_load_grafana=login02_load_grafana,
                                login02_jobs_grafana=login02_jobs_grafana,
                                login03_load_grafana=login03_load_grafana,
                                login03_jobs_grafana=login03_jobs_grafana,
                                login_test_load_grafana=login_test_load_grafana,
                                login_test_jobs_grafana=login_test_jobs_grafana)


@app.route('/login-nodes-xhr/<group_name>', methods=['GET'])
@authenticated
def view_login_nodes_ajax(group_name):
    group, user_status, login_nodes = view_login_nodes_ajax_request(group_name)
    return jsonify(group, user_status, login_nodes)

def view_login_nodes_ajax_request(group_name):
    """
    Get detailed information about OSG login nodes specifically
    """
    query = {'token': ciconnect_api_token,
             'globus_id': session['primary_identity']}

    user = requests.get(ciconnect_api_endpoint + '/v1alpha1/find_user', params=query)
    user = user.json()
    unix_name = user['metadata']['unix_name']

    group = requests.get(ciconnect_api_endpoint + '/v1alpha1/groups/' + group_name, params=query)
    group = group.json()['metadata']
    group_name = group['name']
    # Get User's Group Status
    user_status = requests.get(
                    ciconnect_api_endpoint + '/v1alpha1/groups/' +
                    group_name + '/members/' + unix_name, params=query)
    user_status = user_status.json()['membership']['state']

    # Get all login nodes info
    login_nodes = requests.get(ciconnect_api_endpoint + '/v1alpha1/groups/root.osg.login-nodes/subgroups', params=query)
    login_nodes = login_nodes.json()['groups']
    # Sort login nodes by display name
    login_nodes = sorted(login_nodes, key = lambda i: i['display_name'])

    return group, user_status, login_nodes


@app.route('/login-nodes/<group_name>/users', methods=['GET'])
@authenticated
def view_login_node_users(group_name):
    """Detailed view of Login Node's users"""
    query = {'token': ciconnect_api_token,
             'globus_id': session['primary_identity']}

    if request.method == 'GET':
        # Check if user is Admin of OSG
        user = requests.get(ciconnect_api_endpoint + '/v1alpha1/find_user', params=query)
        user = user.json()
        unix_name = user['metadata']['unix_name']

        group = requests.get(ciconnect_api_endpoint + '/v1alpha1/groups/'
                            + group_name, params=query)
        group = group.json()['metadata']

        return render_template('login_nodes_members.html', group=group, group_name=group_name)


@app.route('/login-nodes/<group_name>/add_users', methods=['GET'])
@authenticated
def view_login_nodes_add_users(group_name):
    """Detailed view of Login Node's non-members"""
    query = {'token': ciconnect_api_token}
    if request.method == 'GET':
        # Get group information
        group = requests.get(ciconnect_api_endpoint + '/v1alpha1/groups/'
                            + group_name, params=query)
        group = group.json()['metadata']

        # Get User's Group Status
        user_status = requests.get(
                        ciconnect_api_endpoint + '/v1alpha1/groups/' +
                        group_name + '/members/' + session['unix_name'], params=query)
        user_status = user_status.json()['membership']['state']
        query = {'token': ciconnect_api_token}
        user_super = requests.get(
                        ciconnect_api_endpoint + '/v1alpha1/users/' + session['unix_name'], params=query)
        try:
            user_super = user_super.json()['metadata']['superuser']
        except:
            user_super = False

        return render_template('login_nodes_add_members.html', group_name=group_name,
                                user_status=user_status, group=group,)


@app.route('/login-nodes-xhr/<group_name>/members', methods=['GET'])
@authenticated
def view_login_node_members_ajax(group_name):
    user_dict = view_login_node_members_ajax_request(group_name)
    print(user_dict)
    return jsonify(user_dict, group_name)

def view_login_node_members_ajax_request(group_name):
    """
    Get detailed information about OSG login nodes specifically
    """
    query = {'token': ciconnect_api_token}
    # Get root base group users, in this case, it would specifically be all OSG users
    enclosing_group_name = '.'.join(group_name.split('.')[:-1])
    enclosing_group = requests.get(ciconnect_api_endpoint + '/v1alpha1/groups/'
                        + 'root.osg' + '/members', params=query)
    enclosing_group = enclosing_group.json()['memberships']
    # print("Enclosing group: {}".format(enclosing_group))
    enclosing_group_members_names = [member['user_name'] for member in enclosing_group]

    # Get login node's specific member's information
    group_members = requests.get(ciconnect_api_endpoint + '/v1alpha1/groups/' + group_name + '/members', params=query)
    memberships = group_members.json()['memberships']
    # print("Memberships: {}".format(memberships))
    memberships_names = [member['user_name'] for member in memberships]
    # Get non-member name
    non_members = list(set(enclosing_group_members_names) - set(memberships_names))

    # Set up multiplex to query all non member's information
    multiplexJson = {}
    user_dict = {}
    # while non_members:
    for user in non_members:
        unix_name = user
        user_query = "/v1alpha1/users/" + unix_name + "?token=" + query['token']
        multiplexJson[user_query] = {"method":"GET"}

    # POST request for multiplex return
    multiplex = requests.post(
        ciconnect_api_endpoint + '/v1alpha1/multiplex', params=query, json=multiplexJson)
    multiplex = multiplex.json()
    for user in multiplex:
        user_name = user.split('/')[3].split('?')[0]
        user_dict[user_name] = json.loads(multiplex[user]['body'])
    # non_members = non_members[10:]
    # multiplexJson = {}
    return user_dict


@app.route('/login-nodes/<group_name>/add_user/<unix_name>', methods=['POST'])
@authenticated
def login_node_add_user(group_name, unix_name):
    if request.method == 'POST':
        query = {'token': session['access_token']}

        put_query = {"apiVersion": 'v1alpha1',
                        'group_membership': {'state': 'active'}}
        # First add user to login nodes umbrella group
        requests.put(ciconnect_api_endpoint + '/v1alpha1/groups/' +
                    'root.osg.login-nodes' + '/members/' + unix_name, params=query, json=put_query)
        # Add user to actual login node group
        user_status = requests.put(
                        ciconnect_api_endpoint + '/v1alpha1/groups/' +
                        group_name + '/members/' + unix_name, params=query, json=put_query)

        if user_status.status_code == requests.codes.ok:
            flash("Successfully added user to login node", 'success')
            return redirect(url_for('view_login_node_users', group_name=group_name))
        else:
            err_message = user_status.json()['message']
            flash('Failed to add user to login node: {}'.format(err_message), 'warning')
            return redirect(url_for('view_login_nodes_add_users', group_name=group_name))


@app.route('/login-nodes/<group_name>/remove_user/<unix_name>', methods=['POST'])
@authenticated
def login_node_remove_user(group_name, unix_name):
    if request.method == 'POST':
        query = {'token': session['access_token']}
        remove_user = requests.delete(
                        ciconnect_api_endpoint + '/v1alpha1/groups/' +
                        group_name + '/members/' + unix_name, params=query)

        if remove_user.status_code == requests.codes.ok:
            flash("Successfully removed user from login node", 'success')
            return redirect(url_for('view_login_node_users', group_name=group_name))
        else:
            err_message = remove_user.json()['message']
            flash('Failed to remove user from login node: {}'.format(err_message), 'warning')
            return redirect(url_for('view_login_node_users', group_name=group_name))


@app.route('/login-nodes/<group_name>/new', methods=['GET', 'POST'])
@authenticated
def create_login_node(group_name):
    token_query = {'token': session['access_token']}
    if request.method == 'GET':
        return render_template('login_nodes_create.html', group_name=group_name)

    elif request.method == 'POST':
        name = request.form['name']
        display_name = request.form['display-name']
        email = request.form['email']
        description = request.form['description']

        put_query = {"apiVersion": 'v1alpha1',
                    'metadata': {'name': name, 'display_name': display_name,
                                'purpose': 'None',
                                'email': email, 'description': description}}

        r = requests.put(
            ciconnect_api_endpoint + '/v1alpha1/groups/' + group_name +
            '/subgroup_requests/' + name, params=token_query, json=put_query)

        if r.status_code == requests.codes.ok:
            flash("Successfully created login node", 'success')
            return redirect(url_for('view_login_nodes'))
        else:
            err_message = r.json()['message']
            flash('Failed to create login node: {}'.format(err_message), 'warning')
            return redirect(url_for('view_login_nodes'))



@app.route('/signup', methods=['GET'])
def signup():
    """Send the user to Globus Auth with signup=1."""
    f = open("portal/templates/markdowns/signup_modal.md", "r")
    g = open("portal/templates/markdowns/signup_instructions.md", "r")
    j = open("portal/templates/markdowns/signup.md", "r")
    signup_modal_md = f.read()
    signup_instructions_md = g.read()
    signup_md = j.read()
    # return redirect(url_for('authcallback', signup=1))
    return render_template('signup.html', signup_modal_md=signup_modal_md, signup_instructions_md=signup_instructions_md, signup_md=signup_md)


@app.route('/login', methods=['GET'])
def login():
    """Send the user to Globus Auth."""
    return redirect(url_for('authcallback'))


@app.route('/logout', methods=['GET'])
@authenticated
def logout():
    """
    - Revoke the tokens with Globus Auth.
    - Destroy the session state.
    - Redirect the user to the Globus Auth logout page.
    """
    client = load_portal_client()

    # Revoke the tokens with Globus Auth
    for token, token_type in (
            (token_info[ty], ty)
            # get all of the token info dicts
            for token_info in session['tokens'].values()
            # cross product with the set of token types
            for ty in ('access_token', 'refresh_token')
            # only where the relevant token is actually present
            if token_info[ty] is not None):
        client.oauth2_revoke_token(
            token, additional_params={'token_type_hint': token_type})

    # Destroy the session state
    session.clear()

    redirect_uri = url_for('home', _external=True)

    ga_logout_url = []
    ga_logout_url.append(app.config['GLOBUS_AUTH_LOGOUT_URI'])
    ga_logout_url.append('?client={}'.format(app.config['PORTAL_CLIENT_ID']))
    ga_logout_url.append('&redirect_uri={}'.format(redirect_uri))
    ga_logout_url.append('&redirect_name=OSG Connect')

    # Redirect the user to the Globus Auth logout page
    return redirect(''.join(ga_logout_url))


@app.route('/profile/new', methods=['GET', 'POST'])
@authenticated
def create_profile():
    identity_id = session.get('primary_identity')
    institution = session.get('institution')
    globus_id = identity_id
    query = {'token': ciconnect_api_token,
             'globus_id': globus_id}

    if request.method == 'GET':
        unix_name = ''
        phone = ''
        public_key = ''
        return render_template('profile_create.html', unix_name=unix_name, phone=phone, public_key=public_key)

    elif request.method == 'POST':
        name = request.form['name']
        unix_name = request.form['unix_name']
        email = request.form['email']
        phone = request.form['phone-number']
        institution = request.form['institution']
        public_key = request.form['sshpubstring']
        try:
            email_preference = request.form['email_preference']
            email_preference = 'on'
        except:
            email_preference = 'off'
        globus_id = session['primary_identity']
        superuser = False
        service_account = False

        additional_metadata = {'OSG:Email_Preference': email_preference}
        # Schema and query for adding users to CI Connect DB
        if public_key:
            post_user = {"apiVersion": 'v1alpha1',
                        'metadata': {'globusID': globus_id, 'name': name, 'email': email,
                                     'phone': phone, 'institution': institution,
                                     'public_key': public_key,
                                     'unix_name': unix_name, 'superuser': superuser,
                                     'service_account': service_account}}
        else:
            post_user = {"apiVersion": 'v1alpha1',
                        'metadata': {'globusID': globus_id, 'name': name, 'email': email,
                                     'phone': phone, 'institution': institution,
                                     'unix_name': unix_name, 'superuser': superuser,
                                     'service_account': service_account}}

        # print("POSTED: {}".format(post_user))
        r = requests.post(ciconnect_api_endpoint + '/v1alpha1/users', params=query, json=post_user)
        if r.status_code == requests.codes.ok:
            r = r.json()['metadata']
            session['name'] = r['name']
            session['email'] = r['email']
            session['phone'] = r['phone']
            session['institution'] = r['institution']
            session['access_token'] = r['access_token']
            session['unix_name'] = r['unix_name']

            # Additional PUT request to set additional attributes metadata
            email_query = {"apiVersion": 'v1alpha1',
                            "data": email_preference}
            set_additional_attr = requests.put(ciconnect_api_endpoint + '/v1alpha1/users/' + r['unix_name'] + '/attributes/OSG:Email_Preference', params=query, json=email_query)
            # print("SET ADD ATTR: {}".format(set_additional_attr))

            # Auto generate group membership into OSG - eventually change to
            # dynamically choose connect site based on URL
            put_query = {"apiVersion": 'v1alpha1',
                            'group_membership': {'state': 'pending'}}
            user_status = requests.put(
                            ciconnect_api_endpoint +
                            '/v1alpha1/groups/root.osg/members/' + unix_name,
                            params=query, json=put_query)

            flash(
                'Account registration successful. A request for Unix account '
                + 'activation on the OSG Connect job submission server has been '
                + 'forwarded to OSG staff.', 'success')
            if 'next' in session:
                redirect_to = session['next']
                session.pop('next')
            else:
                redirect_to = url_for('profile')
            return redirect(url_for('profile'))
        else:
            error_msg = r.json()['message']
            session['email_pref'] = email_preference
            print(name, unix_name, email, phone, institution, public_key, email_preference)
            flash(
                'Failed to create your account: {}'.format(error_msg), 'warning')
            return render_template('profile_create.html', name=name, unix_name=unix_name,
                                    email=email, phone=phone, institution=institution,
                                    public_key=public_key, email_preference=email_preference)


@app.route('/profile/edit/<unix_name>', methods=['GET', 'POST'])
@authenticated
def edit_profile(unix_name):
    identity_id = session.get('primary_identity')
    query = {'token': ciconnect_api_token,
             'globus_id': identity_id}
    user = requests.get(
                ciconnect_api_endpoint + '/v1alpha1/find_user', params=query)
    unix_name = user.json()['metadata']['unix_name']

    if request.method == 'GET':
        # Get user info, pass through as args, convert to json and load input fields
        profile = requests.get(
                    ciconnect_api_endpoint + '/v1alpha1/users/' + unix_name, params=query)
        profile = profile.json()['metadata']

        try:
            additional_attributes = requests.get(ciconnect_api_endpoint + '/v1alpha1/users/'
                                            + unix_name + '/attributes/OSG:Email_Preference', params=query)
            email_preference = additional_attributes.json()['data']
            print(email_preference)
        except:
            email_preference = 'off'

        return render_template('profile_edit.html', profile=profile, unix_name=unix_name, email_preference=email_preference)

    elif request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone-number']
        institution = request.form['institution']
        public_key = request.form['sshpubstring']
        try:
            email_preference = request.form['email_preference']
            email_preference = 'on'
        except:
            email_preference = 'off'

        globus_id = session['primary_identity']
        additional_metadata = {'OSG:Email_Preference': email_preference}
        # Schema and query for adding users to CI Connect DB
        if public_key != ' ':
            post_user = {"apiVersion": 'v1alpha1',
                        'metadata': {'name': name, 'email': email,
                                     'phone': phone, 'institution': institution,
                                     'public_key': public_key,
                                     'additional_attributes': additional_metadata}}
        else:
            post_user = {"apiVersion": 'v1alpha1',
                        'metadata': {'name': name, 'email': email,
                                     'phone': phone, 'institution': institution,
                                     'additional_attributes': additional_metadata}}
        # PUT request to update user information
        r = requests.put(ciconnect_api_endpoint + '/v1alpha1/users/' + unix_name, params=query, json=post_user)
        # Additional PUT request to update user's additional attributes
        email_query = {"apiVersion": 'v1alpha1',
                        "data": email_preference}
        set_additional_attr = requests.put(ciconnect_api_endpoint + '/v1alpha1/users/' + unix_name + '/attributes/OSG:Email_Preference', params=query, json=email_query)
        # print("SET ADD ATTR: {}".format(set_additional_attr))
        # print("Updated User: ", r)

        session['name'] = name
        session['email'] = email
        session['phone'] = phone
        session['institution'] = institution

        flash("Successfully updated profile information", 'success')

        if 'next' in session:
            redirect_to = session['next']
            session.pop('next')
        else:
            redirect_to = url_for('profile')

        return redirect(url_for('profile'))


@app.route('/profile', methods=['GET', 'POST'])
@authenticated
def profile():
    """User profile information. Assocated with a Globus Auth identity."""
    if request.method == 'GET':
        identity_id = session.get('primary_identity')
        query = {'token': ciconnect_api_token,
                 'globus_id': identity_id}
        try:
            user = requests.get(ciconnect_api_endpoint + '/v1alpha1/find_user', params=query)
            user = user.json()
            unix_name = user['metadata']['unix_name']
            user_token = user['metadata']['access_token']

            profile = requests.get(
                        ciconnect_api_endpoint + '/v1alpha1/users/' + unix_name, params=query)
            profile = profile.json()
        except:
            profile = None

        if profile:
            profile = profile['metadata']
            name = profile['name']
            email = profile['email']
            phone = profile['phone']
            institution = profile['institution']
            ssh_pubkey = profile['public_key']
            # Check User's Status in OSG Group specifcally
            user_status = requests.get(ciconnect_api_endpoint + '/v1alpha1/users/' + profile['unix_name'] + '/groups/root.osg', params=query)
            user_status = user_status.json()['membership']['state']
        else:
            flash(
                'Please complete any missing profile fields and press Save.', 'warning')
            return redirect(url_for('create_profile'))

        # Set up multiplex to query all non member's information
        multiplexJson = {}
        user_login_nodes = {}
        for group in profile['group_memberships']:
            if 'root.osg.login-nodes.' in group['name']:
                # user_login_nodes.append(group)
                login_node_query = "/v1alpha1/groups/" + group['name'] + "?token=" + query['token']
                multiplexJson[login_node_query] = {"method":"GET"}
        # POST request for multiplex return
        multiplex = requests.post(
            ciconnect_api_endpoint + '/v1alpha1/multiplex', params=query, json=multiplexJson)
        multiplex = multiplex.json()
        for login_node in multiplex:
            login_node_name = login_node.split('/')[3].split('?')[0]
            user_login_nodes[login_node_name] = json.loads(multiplex[login_node]['body'])

        if request.args.get('next'):
            session['next'] = get_safe_redirect()
        return render_template('profile.html', profile=profile, user_status=user_status, user_login_nodes=user_login_nodes)

    elif request.method == 'POST':
        name = session['name'] = request.form['name']
        email = session['email'] = request.form['email']
        institution = session['institution'] = request.form['institution']
        globus_id = session['primary_identity']
        phone = request.form['phone-number']
        public_key = request.form['sshpubstring']
        superuser = True
        service_account = False

        # flash('Thank you! Your profile has been successfully updated.', 'success')

        if 'next' in session:
            redirect_to = session['next']
            session.pop('next')
        else:
            redirect_to = url_for('profile')

        return redirect(redirect_to)


@app.route('/authcallback', methods=['GET'])
def authcallback():
    """Handles the interaction with Globus Auth."""
    # If we're coming back from Globus Auth in an error state, the error
    # will be in the "error" query string parameter.
    if 'error' in request.args:
        flash("You could not be logged into the portal: " +
              request.args.get('error_description', request.args['error']), 'warning')
        return redirect(url_for('home'))

    # Set up our Globus Auth/OAuth2 state
    redirect_uri = url_for('authcallback', _external=True)

    client = load_portal_client()
    client.oauth2_start_flow(redirect_uri, refresh_tokens=True)

    # If there's no "code" query string parameter, we're in this route
    # starting a Globus Auth login flow.
    if 'code' not in request.args:
        additional_authorize_params = (
            {'signup': 1} if request.args.get('signup') else {})

        auth_uri = client.oauth2_get_authorize_url(
            additional_params=additional_authorize_params)

        return redirect(auth_uri)
    else:
        # If we do have a "code" param, we're coming back from Globus Auth
        # and can start the process of exchanging an auth code for a token.
        code = request.args.get('code')
        tokens = client.oauth2_exchange_code_for_tokens(code)

        id_token = tokens.decode_id_token(client)
        session.update(
            tokens=tokens.by_resource_server,
            is_authenticated=True,
            name=id_token.get('name', ''),
            email=id_token.get('email', ''),
            institution=id_token.get('organization', ''),
            primary_username=id_token.get('preferred_username'),
            primary_identity=id_token.get('sub'),
        )

        access_token = session['tokens']['auth.globus.org']['access_token']
        token_introspect = client.oauth2_token_introspect(token=access_token ,include='identity_set')
        identity_set = token_introspect.data['identity_set']
        profile = None

        for identity in identity_set:
            query = {'token': ciconnect_api_token,
                     'globus_id': identity}
            try:
                r = requests.get(
                    ciconnect_api_endpoint + '/v1alpha1/find_user', params=query)
                if r.status_code == requests.codes.ok:
                    user_info = r.json()
                    user_access_token = user_info['metadata']['access_token']
                    unix_name = user_info['metadata']['unix_name']
                    profile = requests.get(
                                ciconnect_api_endpoint + '/v1alpha1/users/' + unix_name, params=query)
                    profile = profile.json()
                    session['primary_identity'] = identity
            except:
                print("NOTHING HERE: {}".format(identity))

        if profile:
            profile = profile['metadata']
            session['name'] = profile['name']
            session['email'] = profile['email']
            session['phone'] = profile['phone']
            session['institution'] = profile['institution']
            session['access_token'] = profile['access_token']
            session['unix_name'] = profile['unix_name']
            session['url_root'] = request.url_root
            session['admin'] = admin_check(profile['unix_name'])
        else:
            session['url_root'] = request.url_root
            session['email_pref'] = 'off'
            return redirect(url_for('create_profile',
                            next=url_for('profile')))
        return redirect(url_for('profile'))

def admin_check(unix_name):
    """
    Check user status on login, and set return admin status
    :param unix_name: unix name of user
    :return: user's status in OSG specifically
    """
    query = {'token': ciconnect_api_token}
    # Query to return user's membership status in a group, specifically OSG
    r = requests.get(
        ciconnect_api_endpoint + '/v1alpha1/users/' + unix_name + '/groups/root.osg', params=query)
    user_status = r.json()['membership']['state']
    return user_status
