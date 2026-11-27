-- The collector (secret key = service_role) got "permission denied for function purge_old_posts":
-- the init migration revoked EXECUTE from public without granting it back to service_role.
grant execute on function public.purge_old_posts() to service_role;
