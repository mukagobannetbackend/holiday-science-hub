import io
from pathlib import Path
import pytest
from app import create_app
from app.db import get_db

@pytest.fixture()
def app(tmp_path):
    return create_app({'TESTING':True,'SECRET_KEY':'test','DATABASE_PATH':str(tmp_path/'hub.db'),'UPLOAD_DIR':str(tmp_path/'uploads')})
@pytest.fixture()
def client(app): return app.test_client()
def login(client,email,password): return client.post('/login',data={'email':email,'password':password},follow_redirects=True)

def test_landing_and_student_login(client):
    assert client.get('/').status_code==200
    response=login(client,'student@holidayhub.local','Student@123')
    assert response.status_code==200
    assert b'Your learning desk' in response.data
    assert b'S2' in response.data

def test_pending_student_cannot_login(client):
    response=client.post('/login',data={'email':'pending@holidayhub.local','password':'Pending@123'},follow_redirects=True)
    assert b'Sign-in failed' in response.data

def test_student_cannot_open_admin_and_class_scope_is_server_enforced(client):
    login(client,'student@holidayhub.local','Student@123')
    assert client.get('/students').status_code==403
    assert client.get('/timetable').status_code==200
    # S4 lesson/resource IDs are denied even if manually requested.
    with client.application.app_context():
        db=get_db(); db.execute("INSERT INTO resources(title,description,filename,level,class_id,subject_id,topic,uploaded_by,created_at) VALUES('S4 note','','nope.pdf','O-Level',4,1,'Cells',1,'2026-11-07T00:00Z')"); db.commit(); rid=db.execute('SELECT last_insert_rowid()').fetchone()[0]
    assert client.get(f'/resource/{rid}/view').status_code==403

def test_admin_approves_payment_and_audit_exists(client):
    login(client,'admin@holidayhub.local','Admin@123')
    assert b'PENDING PAYMENTS' in client.get('/dashboard').data
    response=client.post('/students/4/approve',follow_redirects=True)
    assert response.status_code==200
    with client.application.app_context():
        assert get_db().execute("SELECT status FROM payments WHERE student_id=4").fetchone()[0]=='Approved/Paid'
        assert get_db().execute("SELECT COUNT(*) FROM audit_logs WHERE action='payment_approved'").fetchone()[0]==1

def test_download_request_requires_admin_approval(client):
    login(client,'student@holidayhub.local','Student@123')
    with client.application.app_context():
        db=get_db(); Path(client.application.config['UPLOAD_DIR']).mkdir(parents=True, exist_ok=True); (Path(client.application.config['UPLOAD_DIR'])/'nope.pdf').write_bytes(b'demo note'); db.execute("INSERT INTO resources(title,description,filename,level,class_id,subject_id,topic,uploaded_by,created_at) VALUES('S2 note','','nope.pdf','O-Level',2,1,'Cells',1,'2026-11-07T00:00Z')"); db.commit(); rid=db.execute('SELECT last_insert_rowid()').fetchone()[0]
    response=client.post('/library',data={'resource_id':rid,'reason':'revision'},follow_redirects=True)
    assert b'Download request sent' in response.data
    assert client.get(f'/resource/{rid}/download').status_code==403
    client.get('/logout'); login(client,'admin@holidayhub.local','Admin@123')
    req=None
    with client.application.app_context(): req=get_db().execute('SELECT id FROM download_requests ORDER BY id DESC LIMIT 1').fetchone()[0]
    client.post(f'/downloads/{req}/approve')
    client.get('/logout'); login(client,'student@holidayhub.local','Student@123')
    assert client.get(f'/resource/{rid}/download').status_code==200

def test_written_test_draft_and_submission_lock(client):
    login(client,'student@holidayhub.local','Student@123')
    response=client.get('/tests'); assert b'Cell structure' in response.data
    response=client.post('/test/1',data={'answer_1':'Membrane answer','answer_2':'Osmosis answer','answer_3':'Difference','action':'draft'},follow_redirects=True)
    assert b'Draft' in response.data
    response=client.post('/test/1',data={'answer_1':'Membrane answer','answer_2':'Osmosis answer','answer_3':'Difference','action':'submit'},follow_redirects=True)
    assert b'Submitted' in response.data
    response=client.post('/test/1',data={'answer_1':'Changed','action':'draft'},follow_redirects=True)
    assert b'already submitted' in response.data

def test_teacher_marks_and_releases(client):
    login(client,'student@holidayhub.local','Student@123')
    client.post('/test/1',data={'answer_1':'a','answer_2':'b','answer_3':'c','action':'submit'})
    client.get('/logout'); login(client,'teacher@holidayhub.local','Teacher@123')
    response=client.get('/marking'); assert b'Approved Student' in response.data
    with client.application.app_context(): sid=get_db().execute('SELECT id FROM submissions LIMIT 1').fetchone()[0]
    response=client.post(f'/mark/{sid}',data={'mark_1':'5','mark_2':'4','mark_3':'5','comment_1':'Good','comment_2':'Clear','comment_3':'Well done'},follow_redirects=True)
    assert b'Marks saved' in response.data
