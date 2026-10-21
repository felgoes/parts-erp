from app.api.routes.push import dismiss_notification, notification_history
from app.models import PushNotification, User


def test_dismissed_notification_is_hidden_only_for_that_user(db):
    first_user = User(email="dismiss-first@example.com", full_name="First", password_hash="unused")
    second_user = User(
        email="dismiss-second@example.com", full_name="Second", password_hash="unused"
    )
    notice = PushNotification(
        dedupe_key="dismissible-1", title="Backup", body="Concluído", category="backup"
    )
    db.add_all([first_user, second_user, notice])
    db.commit()

    dismiss_notification(notice.id, db, first_user)

    assert notification_history(db=db, user=first_user) == []
    assert [item.id for item in notification_history(db=db, user=second_user)] == [notice.id]
    assert db.get(PushNotification, notice.id) is not None
