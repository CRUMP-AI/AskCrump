-- Ask Crump optional-profile growth metric correction.
-- Preserve the server-authoritative event and all counts while making the
-- aggregate label match the intentionally optional product experience.

do $migration$
declare
  v_definition text;
  v_old_count integer;
begin
  select pg_get_functiondef(
    'public.product_growth_funnel_snapshot(timestamptz,timestamptz,text,boolean)'::regprocedure
  )
  into v_definition;

  v_old_count :=
    (length(v_definition) - length(replace(v_definition, '''onboarding_completed''::text', '')))
    / length('''onboarding_completed''::text');

  if v_old_count <> 1 or position('''optional_profile_completed''::text' in v_definition) > 0 then
    raise exception 'Unexpected product growth metric definition; refusing semantic rewrite.'
      using errcode = '55000';
  end if;

  execute replace(
    v_definition,
    '''onboarding_completed''::text',
    '''optional_profile_completed''::text'
  );
end
$migration$;

comment on function public.product_growth_funnel_snapshot(
  timestamptz,
  timestamptz,
  text,
  boolean
) is
  'Service-role-only, content-free aggregate funnel. Stage 4 is optional profile-name completion, not required onboarding or activation. Uses completed chat jobs, Project continuity, and generated files as durable outcomes when best-effort product events are absent; D1/D7 denominators remain activation-based.';
