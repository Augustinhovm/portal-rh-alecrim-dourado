from datetime import date
from app import create_app
from app.extensions import db
from app.models import User, Employee, ROLE_ADMIN, ROLE_MANAGER, ROLE_EMPLOYEE

app=create_app()
with app.app_context():
    if User.query.first():
        print("Banco já possui usuários. Seed não executado.")
    else:
        def add(email,password,role,name,cpf,job,dept,project,manager=None):
            u=User(email=email,role=role);u.set_password(password);db.session.add(u);db.session.flush()
            e=Employee(user_id=u.id,full_name=name,cpf=cpf,job_title=job,department=dept,project=project,admission_date=date.today(),manager_id=manager.id if manager else None)
            db.session.add(e);db.session.flush();return e
        admin=add("rh@associacao.local","Admin@123",ROLE_ADMIN,"Administrador RH","000.000.000-00","RH","Administração","Administração")
        manager=add("gestor@associacao.local","Gestor@123",ROLE_MANAGER,"Responsável de Área","111.111.111-11","Coordenador","Casa Lar","Casa Lar")
        employee=add("colaborador@associacao.local","Colab@123",ROLE_EMPLOYEE,"Colaborador Demonstração","222.222.222-22","Cuidador","Casa Lar","Casa Lar",manager)
        db.session.commit();print("Usuários de demonstração criados.")
        print("RH: rh@associacao.local / Admin@123")
        print("Gestor: gestor@associacao.local / Gestor@123")
        print("Colaborador: colaborador@associacao.local / Colab@123")
