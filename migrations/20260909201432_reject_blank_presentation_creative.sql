-- PostgreSQL CHECK constraints accept UNKNOWN as well as TRUE. Make the two
-- creative-bearing Presentation routes explicitly false when creative is
-- NULL, and mirror that boundary in the service-role AccountCreated writer.

alter table public.product_events
  drop constraint if exists product_events_campaign_registry_check;

alter table public.product_events
  add constraint product_events_campaign_registry_check check (
    (campaign is null and creative is null)
    or (
      campaign = 'presentation-proof-current'
      and intent = 'presentation'
      and (
        (source = 'facebook' and placement = 'profile-link' and creative is null)
        or (source = 'instagram' and placement = 'profile-link' and creative is null)
        or (
          source = 'facebook'
          and placement = 'organic-social'
          and creative = 'fb-static'
          and creative is not null
        )
        or (
          source = 'instagram'
          and placement = 'organic-social'
          and creative = 'ig-story'
          and creative is not null
        )
      )
    )
    or (
      campaign = 'real-product-continuity'
      and source in ('facebook', 'instagram')
      and placement in ('profile-link', 'organic-social')
      and intent = 'projects'
      and (creative is null or creative in ('continuity-feed', 'continuity-story'))
    )
    or (
      campaign = 'rough-to-useful-v2'
      and source = 'facebook'
      and placement = 'organic-social'
      and intent = 'projects'
      and (creative is null or creative = 'rough-to-useful-current-feed')
    )
    or (
      campaign = 'rough-idea-launch-plan'
      and source = 'organic-search'
      and placement = 'workflow-guide'
      and intent = 'projects'
      and (creative is null or creative = 'search-article')
    )
    or (
      campaign = 'project-memory-boundaries'
      and source in ('organic-search', 'facebook', 'instagram')
      and placement in ('workflow-guide', 'organic-social')
      and intent = 'projects'
      and (
        creative is null
        or creative in ('search-article', 'project-memory-feed', 'project-memory-story')
      )
    )
    or (
      campaign = 'editable-powerpoint-review'
      and source in ('organic-search', 'facebook', 'instagram')
      and placement in ('workflow-guide', 'organic-social')
      and intent = 'presentation'
      and (
        creative is null
        or creative in ('search-article', 'presentation-feed', 'presentation-story')
      )
    )
    or (
      campaign = 'creator-cohort-01'
      and source = 'founder-outreach'
      and placement = 'creator-cohort'
      and intent = 'projects'
      and (creative is null or creative = 'personal-invite')
    )
  ) not valid;

alter table public.product_events
  validate constraint product_events_campaign_registry_check;

create or replace function public.record_account_created_event(
  p_user_id uuid,
  p_event_key text,
  p_environment text,
  p_client_platform text,
  p_acquisition text default null,
  p_placement text default null,
  p_campaign text default null,
  p_creative text default null,
  p_intent text default null
)
returns boolean
language plpgsql
security invoker
set search_path = ''
as $function$
declare
  v_acquisition text := lower(btrim(coalesce(p_acquisition, '')));
  v_placement text := lower(btrim(coalesce(p_placement, '')));
  v_campaign text := lower(btrim(coalesce(p_campaign, '')));
  v_creative text := nullif(lower(btrim(coalesce(p_creative, ''))), '');
  v_intent text := lower(btrim(coalesce(p_intent, '')));
begin
  if v_acquisition not in (
    'direct', 'instagram', 'facebook', 'facebook-pinned', 'linkedin',
    'tiktok', 'youtube', 'x', 'referral', 'organic', 'organic-search',
    'clevercrump', 'founder-outreach'
  ) then
    v_acquisition := null;
  end if;

  if v_placement not in (
    'response-share', 'profile-link', 'workflow-guide', 'organic-social',
    'creator-cohort'
  ) then
    v_placement := null;
  end if;

  if v_intent not in (
    'document', 'presentation', 'resume', 'video', 'projects'
  ) then
    v_intent := null;
  end if;

  if not (
    (
      v_campaign = 'presentation-proof-current'
      and v_intent = 'presentation'
      and (
        (v_acquisition = 'facebook' and v_placement = 'profile-link' and v_creative is null)
        or (v_acquisition = 'instagram' and v_placement = 'profile-link' and v_creative is null)
        or (
          v_acquisition = 'facebook'
          and v_placement = 'organic-social'
          and v_creative = 'fb-static'
          and v_creative is not null
        )
        or (
          v_acquisition = 'instagram'
          and v_placement = 'organic-social'
          and v_creative = 'ig-story'
          and v_creative is not null
        )
      )
    )
    or (
      v_campaign = 'real-product-continuity'
      and v_acquisition in ('facebook', 'instagram')
      and v_placement in ('profile-link', 'organic-social')
      and v_intent = 'projects'
    )
    or (
      v_campaign = 'rough-to-useful-v2'
      and v_acquisition = 'facebook'
      and v_placement = 'organic-social'
      and v_intent = 'projects'
    )
    or (
      v_campaign = 'rough-idea-launch-plan'
      and v_acquisition = 'organic-search'
      and v_placement = 'workflow-guide'
      and v_intent = 'projects'
    )
    or (
      v_campaign = 'project-memory-boundaries'
      and v_acquisition in ('organic-search', 'facebook', 'instagram')
      and v_placement in ('workflow-guide', 'organic-social')
      and v_intent = 'projects'
    )
    or (
      v_campaign = 'editable-powerpoint-review'
      and v_acquisition in ('organic-search', 'facebook', 'instagram')
      and v_placement in ('workflow-guide', 'organic-social')
      and v_intent = 'presentation'
    )
    or (
      v_campaign = 'creator-cohort-01'
      and v_acquisition = 'founder-outreach'
      and v_placement = 'creator-cohort'
      and v_intent = 'projects'
    )
  ) then
    v_campaign := null;
  end if;

  if v_campaign is null or not (
    (
      v_campaign = 'presentation-proof-current'
      and (
        (v_acquisition = 'facebook' and v_placement = 'profile-link' and v_creative is null)
        or (v_acquisition = 'instagram' and v_placement = 'profile-link' and v_creative is null)
        or (
          v_acquisition = 'facebook'
          and v_placement = 'organic-social'
          and v_creative = 'fb-static'
          and v_creative is not null
        )
        or (
          v_acquisition = 'instagram'
          and v_placement = 'organic-social'
          and v_creative = 'ig-story'
          and v_creative is not null
        )
      )
    )
    or (v_campaign = 'real-product-continuity' and v_creative in ('continuity-feed', 'continuity-story'))
    or (v_campaign = 'rough-to-useful-v2' and v_creative = 'rough-to-useful-current-feed')
    or (v_campaign = 'rough-idea-launch-plan' and v_creative = 'search-article')
    or (v_campaign = 'project-memory-boundaries' and v_creative in ('search-article', 'project-memory-feed', 'project-memory-story'))
    or (v_campaign = 'editable-powerpoint-review' and v_creative in ('search-article', 'presentation-feed', 'presentation-story'))
    or (v_campaign = 'creator-cohort-01' and v_creative = 'personal-invite')
  ) then
    v_creative := null;
  end if;

  insert into public.product_events (
    user_id,
    event_name,
    event_key,
    environment,
    client_platform,
    source,
    placement,
    campaign,
    creative,
    intent
  ) values (
    p_user_id,
    'AccountCreated',
    p_event_key,
    p_environment,
    p_client_platform,
    v_acquisition,
    v_placement,
    v_campaign,
    v_creative,
    v_intent
  )
  on conflict (user_id, event_name, event_key, environment) do nothing;

  return found;
end;
$function$;

revoke execute on function public.record_account_created_event(
  uuid, text, text, text, text, text, text, text, text
) from public, anon, authenticated;
grant execute on function public.record_account_created_event(
  uuid, text, text, text, text, text, text, text, text
) to service_role;

comment on function public.record_account_created_event(
  uuid, text, text, text, text, text, text, text, text
) is
  'Service-role-only idempotent AccountCreated writer. Discards unknown first-touch labels and stores no referrer, URL, search term, content, filename, email, or arbitrary metadata.';
