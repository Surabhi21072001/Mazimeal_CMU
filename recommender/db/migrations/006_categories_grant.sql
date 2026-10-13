-- The household_members trigger derives each member's DRI category through
-- fn_derive_category_id, which reads public.categories as the calling user.
-- categories had a public-read policy but no table grant, so saving a member
-- with an age and sex failed with "permission denied for table categories".
-- Same grant as recommender/db/95_rls.sql. Re-runnable.
--
--   psql "$DATABASE_URL" -f recommender/db/migrations/006_categories_grant.sql

DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        GRANT SELECT ON public.categories TO anon, authenticated;
    END IF;
END $$;
