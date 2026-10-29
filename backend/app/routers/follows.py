from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Follow, User
from ..schemas import FollowIn
from ..deps import current_user

router = APIRouter()

@router.post("")
def follow(data: FollowIn, db: Session = Depends(get_db), user=Depends(current_user)):
    if data.user_id == user.id:
        raise HTTPException(400, "Hawezi kujifuata mwenyewe")
    target = db.query(User).filter(User.id == data.user_id).first()
    if not target:
        raise HTTPException(404, "Mtumiaji hapatikani")
    existing = db.query(Follow).filter(Follow.follower_id == user.id, Follow.following_id == data.user_id).first()
    if existing:
        return {"message": "Already following"}
    count = db.query(Follow).filter(Follow.follower_id == user.id).count()
    if count >= 2:
        raise HTTPException(400, "Unaweza kufuata watumiaji 2 tu. Acha kufuata mmoja kwanza.")
    f = Follow(follower_id=user.id, following_id=data.user_id)
    db.add(f)
    db.commit()
    return {"message": "Followed"}

@router.delete("/{user_id}")
def unfollow(user_id: str, db: Session = Depends(get_db), user=Depends(current_user)):
    f = db.query(Follow).filter(Follow.follower_id == user.id, Follow.following_id == user_id).first()
    if not f:
        raise HTTPException(404, "Hufuatii")
    db.delete(f)
    db.commit()
    return {"message": "Unfollowed"}

@router.get("/me")
def my_follows(db: Session = Depends(get_db), user=Depends(current_user)):
    follows = db.query(Follow).filter(Follow.follower_id == user.id).all()
    result = []
    for f in follows:
        u = f.following
        result.append({"id": u.id, "nickname": u.nickname, "followed_at": f.created_at.isoformat()})
    return result