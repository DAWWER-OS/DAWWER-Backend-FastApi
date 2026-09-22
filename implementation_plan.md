# خطة استبدال وتحديث نماذج البيانات (Models) بناءً على قاعدة بيانات Supabase

تم فحص قاعدة بيانات Supabase المتصلة بنجاح، ووجدنا **17 جدولاً فعلياً** في مخطط `public` مع بيانات قائمة (مثل 2007 منتج، ومستخدمين، ومتاجر، وتصنيفات، وصلاحيات).
الجداول الموجودة حالياً داخل مجلد `app/models/` غير مكتملة الحقول وتفتقر لمعظم الجداول والربط الأساسي في Supabase.

تهدف هذه الخطة إلى:
1. حذف وإعادة كتابة نماذج الجداول (`app/models/`) القديمة بالكامل.
2. استدعاء وإنشاء نماذج SQLAlchemy لجميع الجداول الـ 17 الموجودة في Supabase بأدق تفاصيل الأنواع والقيود (UUIDs, Foreign Keys, Defaults, Timestamps).
3. معالجة مشكلة اتصال `psycopg2` مع `?pgbouncer=true` في رابط الاتصال ليعمل بسلاسة.
4. تحديث الـ Schemas (Pydantic) والخدمات المرتبطة لدعم كافة الحقول الجديدة المتوفرة في قاعدة بيانات سوبا.

---

## User Review Required

> [!IMPORTANT]
> قاعدة بيانات Supabase تحتوي على بيانات فعلية (مثل 2007 منتج في `store_products` ومتجر ومستخدمين).
> التعديلات ستتم داخل كود الباك إند (`app/models/` و `app/schemas/`) ولن تقوم بحذف أي بيانات من داخل Supabase إطلاقاً، بل ستجعل كود الباك إند متطابقاً 100% مع الجداول الفعلية في Supabase.

---

## الجداول المستخرجة من Supabase (17 جدول)

| # | اسم الجدول في Supabase | اسم الموديل (Model Class) | الملف المستهدف |
|---|---|---|---|
| 1 | `users` | `User` | [user.py](file:///d:/DAWEROS/app/models/user.py) |
| 2 | `stores` | `Store` | [store.py](file:///d:/DAWEROS/app/models/store.py) |
| 3 | `categories` | `Category` | [category.py](file:///d:/DAWEROS/app/models/category.py) [NEW] |
| 4 | `store_products` | `StoreProduct` | [product.py](file:///d:/DAWEROS/app/models/product.py) |
| 5 | `import_jobs` | `ImportJob` | [import_job.py](file:///d:/DAWEROS/app/models/import_job.py) |
| 6 | `shelf_jobs` | `ShelfJob` | [shelf_job.py](file:///d:/DAWEROS/app/models/shelf_job.py) |
| 7 | `draft_products` | `DraftProduct` | [shelf_job.py](file:///d:/DAWEROS/app/models/shelf_job.py) |
| 8 | `store_roles` | `StoreRole` | [store_rbac.py](file:///d:/DAWEROS/app/models/store_rbac.py) [NEW] |
| 9 | `store_permissions` | `StorePermission` | [store_rbac.py](file:///d:/DAWEROS/app/models/store_rbac.py) [NEW] |
| 10 | `store_role_permissions` | `StoreRolePermission` | [store_rbac.py](file:///d:/DAWEROS/app/models/store_rbac.py) [NEW] |
| 11 | `store_staff` | `StoreStaff` | [store_rbac.py](file:///d:/DAWEROS/app/models/store_rbac.py) [NEW] |
| 12 | `store_staff_permissions` | `StoreStaffPermission` | [store_rbac.py](file:///d:/DAWEROS/app/models/store_rbac.py) [NEW] |
| 13 | `store_documents` | `StoreDocument` | [store_document.py](file:///d:/DAWEROS/app/models/store_document.py) [NEW] |
| 14 | `refresh_tokens` | `RefreshToken` | [auth.py](file:///d:/DAWEROS/app/models/auth.py) [NEW] |
| 15 | `revoked_tokens` | `RevokedToken` | [auth.py](file:///d:/DAWEROS/app/models/auth.py) [NEW] |
| 16 | `verification_codes` | `VerificationCode` | [auth.py](file:///d:/DAWEROS/app/models/auth.py) [NEW] |
| 17 | `audit_logs` | `AuditLog` | [audit_log.py](file:///d:/DAWEROS/app/models/audit_log.py) [NEW] |

---

## Proposed Changes

### 1. Database Connection Fix
#### [MODIFY] [session.py](file:///d:/DAWEROS/app/db/session.py) & [.env](file:///d:/DAWEROS/.env)
- إزالة/تنظيف المعامل `?pgbouncer=true` الذي يرفضه `psycopg2` وتجهيز الـ engine ليتصل بسلاسة عبر pooler port `5432` أو `6543` مع `sslmode=require`.

### 2. SQLAlchemy Models
#### [MODIFY] [user.py](file:///d:/DAWEROS/app/models/user.py)
- إعادة كتابة الموديل لدعم كافة حقول جدول `users` في Supabase:
  - `id`: UUID (PK, `as_uuid=False`)
  - `full_name`, `email`, `phone_number`, `password_hash`, `role`, `status`
  - `is_email_verified`, `email_verified_at`, `is_phone_verified`, `phone_verified_at`, `last_login_at`
  - `created_at`, `updated_at`, `created_by`, `updated_by`

#### [MODIFY] [store.py](file:///d:/DAWEROS/app/models/store.py)
- إعادة كتابة الموديل ليشمل كافة الحقول الكاملة لجدول `stores`:
  - `id`: UUID (PK, `as_uuid=False`), `owner_id`: UUID (FK -> `users.id`)
  - `name`, `description`, `commercial_registration_number`, `tax_number`, `phone_number`, `email`, `address`, `city`
  - `latitude`, `longitude`, `logo_url`, `cover_image_url`, `verification_status`, `status`
  - `rejection_reason`, `information_request_message`, `submitted_at`, `reviewed_at`, `reviewed_by_id`, `approved_at`, `suspended_at`, `suspension_reason`
  - `created_at`, `updated_at`, `created_by`, `updated_by`, `is_active`

#### [NEW] [category.py](file:///d:/DAWEROS/app/models/category.py)
- نموذج جدول `categories`:
  - `id`: UUID (PK), `name`, `description`, `icon_url`, `is_active`, `display_order`
  - `parent_category_id`: UUID (FK -> `categories.id`)
  - `created_at`, `updated_at`, `created_by`, `updated_by`

#### [MODIFY] [product.py](file:///d:/DAWEROS/app/models/product.py)
- تحديث نموذج `store_products` ليتطابق بالكامل مع الأعمدة وأنواع البيانات الموجودة (16 عمود).

#### [MODIFY] [import_job.py](file:///d:/DAWEROS/app/models/import_job.py)
- تحديث نموذج `import_jobs` ليتطابق مع أعمدة Supabase (10 أعمدة).

#### [MODIFY] [shelf_job.py](file:///d:/DAWEROS/app/models/shelf_job.py)
- تحديث نماذج `shelf_jobs` (11 عمود) و `draft_products` (16 عمود).

#### [NEW] [store_rbac.py](file:///d:/DAWEROS/app/models/store_rbac.py)
- تعريف نماذج إدارة الأدوار والصلاحيات للمتاجر:
  - `StoreRole` (`store_roles`)
  - `StorePermission` (`store_permissions`)
  - `StoreRolePermission` (`store_role_permissions`)
  - `StoreStaff` (`store_staff`)
  - `StoreStaffPermission` (`store_staff_permissions`)

#### [NEW] [store_document.py](file:///d:/DAWEROS/app/models/store_document.py)
- نموذج `StoreDocument` (`store_documents`) للمستندات والملفات المرفوعة.

#### [NEW] [auth.py](file:///d:/DAWEROS/app/models/auth.py)
- نماذج الأمان وتوثيق الجلسات:
  - `RefreshToken` (`refresh_tokens`)
  - `RevokedToken` (`revoked_tokens`)
  - `VerificationCode` (`verification_codes`)

#### [NEW] [audit_log.py](file:///d:/DAWEROS/app/models/audit_log.py)
- نموذج سجلات العمليات `AuditLog` (`audit_logs`).

#### [MODIFY] [__init__.py](file:///d:/DAWEROS/app/models/__init__.py)
- تصدير كافة النماذج الجديدة لتكون متاحة بشكل موحد.

### 3. Pydantic Schemas & Endpoints Sync
#### [MODIFY] [user.py](file:///d:/DAWEROS/app/schemas/user.py)
- توسيع `UserProfileResponse` و `UserProfileUpdate` لتغطية حقول المستخدم الإضافية.

#### [MODIFY] [store.py](file:///d:/DAWEROS/app/schemas/store.py)
- توسيع `StoreResponse` و `StoreCreate` لتغطية كافة تفاصيل المتجر المضافة.

---

## Verification Plan

### Automated Tests
- تشغيل اختبارات الاستعلام المباشرة عبر ORM للتحقق من قراءة البيانات من الجداول الـ 17 في Supabase.
- تشغيل `pytest` للتأكد من أن جميع الـ endpoints والاختبارات تعمل بدون أخطاء.

### Manual Verification
- التحقق من تشغيل تطبيق FastAPI (`uvicorn app.main:app`) وفحص سلامة التوجيهات وقراءة المنتجات (2007 منتج) والمتاجر من Supabase.
