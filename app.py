from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, send, emit, join_room, leave_room
from datetime import datetime, UTC
from functions.functions import gen_code, compare_group_dates
import time

'''
make it so when a group is joined/made all users get it on their screen without refresh
current thought, broadcast and only respond if the user id is in the new group to make other
user/users be in that group and add group to their screen.
'''


app = Flask(__name__)
app.config["SECRET_KEY"] = "chat_app"
app.config["SQLALCHEMY_DATABASE_URI"] = 'sqlite:///test.db'
db = SQLAlchemy(app)
socketio = SocketIO(app)

class User(db.Model):
    id = db.Column(db.String(200), primary_key=True)
    username = db.Column(db.String(200))
    password = db.Column(db.String(200))
    date_created = db.Column(db.DateTime, default = datetime.now())

class Group(db.Model):
    group_id = db.Column(db.String(200), primary_key=True)
    group_name = db.Column(db.String(200))
    date_created = db.Column(db.DateTime, default = datetime.now())

class GroupMembership(db.Model):
    id = db.Column(db.String(200), primary_key = True)
    group_id = db.Column(db.String(200))
    user_id = db.Column(db.String(200))
    last_message_read = db.Column(db.Boolean, default = False)

class Message(db.Model):
    id = db.Column(db.String(200), primary_key=True)
    group_id = db.Column(db.String(200))
    username = db.Column(db.String(200))
    content = db.Column(db.String(200))
    date_created = db.Column(db.DateTime, default = datetime.now())

with app.app_context():
   db.create_all()

@app.route('/', methods=["POST", "GET"])
def index():

    if not session.get("username"):
        return redirect(url_for("login"))

    user = User.query.filter_by(username = session.get("username")).scalar()
    users = User.query.order_by(User.date_created).all()

    user_groups = GroupMembership.query.filter_by(user_id = user.id).all() #find what groups user is in server side then send groups, not group meberships

    user_groups_list = []

    for group in user_groups:
        group_name = Group.query.filter_by(group_id = group.group_id).scalar().group_name
        group_date = Group.query.filter_by(group_id = group.group_id).scalar().date_created
        group_message_date = Message.query.filter_by(group_id = group.group_id).order_by(Message.date_created.desc()).first()  
        
        last_message_date = 0
        
        if group_message_date:
            last_message_date = time.mktime(group_message_date.date_created.timetuple())
        else :
            last_message_date = time.mktime(group_date.timetuple())

        if group_name == "*":
            other_user_id = GroupMembership.query.filter(GroupMembership.group_id == group.group_id, GroupMembership.user_id != user.id).scalar()
            if not other_user_id:
                continue
            other_user_id = other_user_id.user_id
            group_name = User.query.filter_by(id = other_user_id).scalar().username

        user_groups_list.append({
            "group_id" : group.group_id,
            "group_name" : group_name,
            "date_created" : group_date,
            "last_message_time" : last_message_date,
            "last_message_read" : group.last_message_read,
        })

    user_groups_list.sort(reverse=True, key=compare_group_dates)

    for group in user_groups_list:
        print(group["group_name"] + "   :   " + str(group["last_message_read"]))

    #user_groups_list = []

    return render_template('index.html', users=users, user = user, userGroupsList = user_groups_list)



@app.route('/login', methods=['POST', "GET"])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        login = request.form.get('login', False)
        new_account = request.form.get('new_account', False)

        if new_account:
            return redirect(url_for('new_account'))

        if not username:
            return render_template('login.html', error = "please input a username", username = username)
        
        if not password:
            return render_template('login.html', error = "please input a password", username = username)
        
        user = User.query.filter_by(username = username).scalar()

        if not user or password != user.password:
            return render_template("login.html", error = "username or password is incorrect", username = username)
        
        session["username"] = username

        return redirect(url_for("index"))


    users = User.query.order_by(User.date_created).all()
    return render_template('login.html', users = users)

@app.route('/new_account', methods=["POST", "GET"])
def new_account():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        rewrite_password = request.form['rewritePassword']

        if not username:
            return render_template('new_account.html', error = "please input a username", username = username)
        
        if not password:
            return render_template('new_account.html', error = "please input a password", username = username)

        if password != rewrite_password:
            return render_template('new_account.html', error = "passwords don't match", username = username)
        
        if User.query.filter_by(username = username).scalar():
            return render_template('new_account.html', error = "username already taken", username = username)
        
        new_user = User(id=gen_code(), username=username, password=password)

        try :
            db.session.add(new_user)
            db.session.commit()
            print(new_user.username)           
            redirect("/")
        except:
            return "ERROR"

        session["username"] = username

        return redirect(url_for("index"))

    return render_template("new_account.html")

@socketio.on('message')
def message(data):
    content = {
        'groupId': session.get('group'),
        'username': session.get('username'),
        'content' : data['data'],
        'dateCreated': datetime.now().strftime("%x, %X")
    }
    print(content)
    send(content, to=session.get('group'))

    new_message = Message(id=gen_code(), group_id=session.get("group"), username = session.get("username"), content = content["content"], date_created = datetime.now())
    ##print(new_message)
    try:
        db.session.add(new_message)
        db.session.commit()
        print(new_message)
        redirect("/")
    except:
        return 'ERROR'

@socketio.on("enterGroup")
def enterGroup(data):
    session["group"] = data['data']
    new_group = session.get('group')
    join_room(new_group)

    try:

        cur_user_id = User.query.filter_by(username = session.get("username")).scalar().id

        user_group_membership = GroupMembership.query.filter_by(group_id = session.get('group'), user_id = cur_user_id) #.update({GroupMembership.last_message_read: True})

        user_group_membership.update({GroupMembership.last_message_read: True})    

        db.session.commit()

        print(user_group_membership.scalar().last_message_read)
    except:
        return "ERROR"


    ## test to see if not leaving rooms is a problem, if a messsage goes to all rooms
    ## then have a different emit to leave group in the javascript that will leave the room first
    group_messages = Message.query.filter_by(group_id = new_group).all()  #filter_by(group_id = new_group)

    messages = []

    for message in group_messages:
        message_dict = {
            "groupId": message.group_id,
            "username": message.username,
            "content": message.content,
            "dateCreated": message.date_created.strftime("%x, %X")
        }
        messages.append(message_dict)

    emit("message_list", messages)

    print(datetime.now())


@socketio.on("leaveGroup")
def leaveGroup(data):
    print(data["data"])
    cur_group = data["data"]
    leave_room(cur_group)


@socketio.on("userSearch")
def userSearch(data):
    searched_name = data['data']
    print(data["data"])
    user_searched = User.query.filter_by(username = searched_name).scalar()
    cur_user = User.query.filter_by(username = session.get("username")).scalar()

    if not user_searched:
        print("no such user")
        return

    groups_user_in = GroupMembership.query.filter_by(user_id = cur_user.id).all()

    #groups_searched_user_in = GroupMembership.query.filter_by(user_id = user_searched.id).all()

    #common_groups = session.query(groups_user_in.group_id).join(groups_searched_user_in, groups_user_in.group_id == groups_searched_user_in.group_id).all()

    for group_membership in groups_user_in:
        print(group_membership.id + "  " + group_membership.group_id + " " + group_membership.user_id)
        #get group memberships where both users are in that group but is not a the membership of them
        # if theres no one else in that group theres only those two and its their mutual group 
        test = GroupMembership.query.filter(GroupMembership.group_id == group_membership.group_id, GroupMembership.user_id != user_searched.id, GroupMembership.user_id != cur_user.id).scalar()
        print(test)
        if not test:
            emit("join_this_group", searched_name)
            return
            
    new_group_id = gen_code()
    
    new_group = Group(group_id = new_group_id, group_name = "*")

    user_searched_membership = GroupMembership(id = gen_code(), group_id = new_group_id, user_id = user_searched.id)

    cur_user_membership = GroupMembership(id = gen_code(), group_id = new_group_id, user_id = cur_user.id)
    
    try:
        db.session.add(new_group)
        db.session.add_all([user_searched_membership, cur_user_membership])
        db.session.commit()
        print("group made")
        redirect("/")
    except:
        print("error")
        return 'ERROR'
    print(GroupMembership.query.all())

    emit("new_group_made", {
        "usernames": [user_searched.username, cur_user.username],
        "user_ids": [user_searched.id, cur_user.id],
        "group_id": new_group.group_id,
        "group_name": new_group.group_name 
    }, broadcast=True)
    
    #emit broadcast to add mebers in group

    print(data)

@socketio.on('connect')
def connect(auth):
    print("connected")

@socketio.on("disconnect")
def disconnect():
    print('disconnected')
    group = session.get("group")
    leave_room(group)



if __name__ == '__main__':
    app.run(debug = True)