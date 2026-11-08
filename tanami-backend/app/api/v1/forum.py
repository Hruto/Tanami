"""Forum routes (``design.md`` 10.10, 13).

Reading is public (design 13: forum content is public), so the list, detail and
comment routes accept an optional bearer token: an author then also sees their
own hidden post, and a moderator sees everything. Writing always needs a session.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Query, Response, UploadFile, status

from app.api.deps import (
    CurrentUser,
    ForumServiceDep,
    OptionalUser,
    SettingsDep,
    StorageDep,
)
from app.core.errors import ValidationError
from app.core.pagination import encode_cursor, page_request
from app.providers.images import new_object_key, validate_and_normalise
from app.schemas.base import Envelope, ListEnvelope, PaginationMeta
from app.schemas.forum import (
    ForumCategoryOut,
    ForumCommentCreate,
    ForumCommentOut,
    ForumImageOut,
    ForumPostCreate,
    ForumPostDetailOut,
    ForumPostOut,
    ForumReportCreate,
    ForumReportOut,
)

router = APIRouter(tags=["forum"])


@router.get("/forum/categories")
async def list_categories(service: ForumServiceDep) -> ListEnvelope[ForumCategoryOut]:
    categories = await service.categories()
    return ListEnvelope(
        data=[ForumCategoryOut(**category) for category in categories],
        meta=PaginationMeta(next_cursor=None, has_more=False),
    )


@router.get("/forum/posts")
async def list_posts(
    service: ForumServiceDep,
    viewer: OptionalUser,
    commodity_code: Annotated[str | None, Query(max_length=32)] = None,
    q: Annotated[str | None, Query(max_length=120)] = None,
    limit: Annotated[int | None, Query(ge=1, le=50)] = None,
    cursor: Annotated[str | None, Query()] = None,
) -> ListEnvelope[ForumPostOut]:
    """Published posts, newest first, filterable by commodity and free text."""
    page = page_request(limit, cursor)
    posts = await service.list_posts(
        commodity_code=commodity_code,
        query=q,
        limit=page.limit + 1,
        cursor=page.cursor,
        viewer=viewer,
    )
    has_more = len(posts) > page.limit
    posts = posts[: page.limit]
    next_cursor = (
        encode_cursor(posts[-1].created_at, UUID(posts[-1].id)) if has_more and posts else None
    )
    return ListEnvelope(data=posts, meta=PaginationMeta(next_cursor=next_cursor, has_more=has_more))


@router.post("/forum/posts", status_code=status.HTTP_201_CREATED)
async def create_post(
    payload: ForumPostCreate, user: CurrentUser, service: ForumServiceDep
) -> Envelope[ForumPostOut]:
    post = await service.create_post(
        user,
        commodity_code=payload.commodity_code,
        title=payload.title,
        body=payload.body,
        scan_id=payload.scan_id,
        image_keys=payload.image_keys,
    )
    return Envelope(data=await service.get_post_out(post.id, user))


@router.get("/forum/posts/{post_id}")
async def get_post(
    post_id: UUID, service: ForumServiceDep, viewer: OptionalUser
) -> Envelope[ForumPostDetailOut]:
    return Envelope(data=await service.get_post_detail(post_id, viewer))


@router.delete("/forum/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(post_id: UUID, user: CurrentUser, service: ForumServiceDep) -> Response:
    await service.delete_post(user, post_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/forum/posts/{post_id}/like")
async def like_post(
    post_id: UUID, user: CurrentUser, service: ForumServiceDep
) -> Envelope[ForumPostOut]:
    """Like a post (idempotent; requirement 5 "Interaksi Pengguna")."""
    return Envelope(data=await service.set_like(user, post_id, liked=True))


@router.delete("/forum/posts/{post_id}/like")
async def unlike_post(
    post_id: UUID, user: CurrentUser, service: ForumServiceDep
) -> Envelope[ForumPostOut]:
    return Envelope(data=await service.set_like(user, post_id, liked=False))


@router.get("/forum/posts/{post_id}/comments")
async def list_comments(
    post_id: UUID, service: ForumServiceDep, viewer: OptionalUser
) -> ListEnvelope[ForumCommentOut]:
    post, _ = await service.get_post(post_id, viewer)
    comments = await service.list_comments(post.id, viewer)
    return ListEnvelope(data=comments, meta=PaginationMeta(next_cursor=None, has_more=False))


@router.post("/forum/posts/{post_id}/comments", status_code=status.HTTP_201_CREATED)
async def create_comment(
    post_id: UUID,
    payload: ForumCommentCreate,
    user: CurrentUser,
    service: ForumServiceDep,
) -> Envelope[ForumCommentOut]:
    return Envelope(data=await service.create_comment(user, post_id, payload.body))


@router.delete("/forum/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment(comment_id: UUID, user: CurrentUser, service: ForumServiceDep) -> Response:
    await service.delete_comment(user, comment_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/forum/reports", status_code=status.HTTP_201_CREATED)
async def report_content(
    payload: ForumReportCreate, user: CurrentUser, service: ForumServiceDep
) -> Envelope[ForumReportOut]:
    report = await service.report(
        user,
        target_type=payload.target_type,
        target_id=payload.target_id,
        reason=payload.reason,
        note=payload.note,
    )
    return Envelope(
        data=ForumReportOut(
            id=str(report.id),
            target_type=report.target_type,
            target_id=str(report.target_id),
            reason=report.reason,
            created_at=report.created_at,
        )
    )


@router.post("/uploads/forum-image", status_code=status.HTTP_201_CREATED)
async def upload_forum_image(
    user: CurrentUser,
    settings: SettingsDep,
    storage: StorageDep,
    image: Annotated[UploadFile, File()],
) -> Envelope[ForumImageOut]:
    """One photo for a forum post.

    Same validation as a scan upload - content sniffing, size and dimension
    limits, EXIF stripped by re-encoding - because it comes from the same camera
    roll and TQA 9 does not exempt uploads to the community tab.
    """
    raw = await image.read()
    if not raw:
        raise ValidationError("Foto wajib diisi.", details={"field": "image"})

    validated = validate_and_normalise(
        raw,
        max_bytes=settings.max_scan_upload_bytes,
        max_side=settings.max_image_side,
        max_pixels=settings.max_image_pixels,
    )
    key = new_object_key("forum", user_id=str(user.id), extension=validated.extension)
    await storage.put(key, validated.data, validated.content_type)
    return Envelope(data=ForumImageOut(image_key=key, image_url=storage.public_url(key)))
