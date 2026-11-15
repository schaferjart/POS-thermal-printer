-- ParaBot moves out of public into its own schema (one schema per project
-- in this Supabase project). Policies, grants and the FK move with the tables.
-- n8n's Supabase node must now use schema "parabot".

create schema if not exists parabot;
grant usage on schema parabot to anon, authenticated, service_role;

alter table public.users_ch    set schema parabot;
alter table public.receipts_ch set schema parabot;
alter function public.update_updated_at_column() set schema parabot;
