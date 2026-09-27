create extension if not exists "pgcrypto";

create table if not exists users (
  id uuid primary key default gen_random_uuid(),
  email text unique,
  created_at timestamptz not null default now()
);

create table if not exists commodities (
  id bigserial primary key,
  name text not null unique,
  created_at timestamptz not null default now()
);

create table if not exists markets (
  id bigserial primary key,
  market_code text unique,
  name text not null,
  district text,
  state text,
  created_at timestamptz not null default now()
);

create table if not exists market_data (
  id bigserial primary key,
  report_date date not null,
  market_code text,
  market text not null,
  district text,
  state text,
  commodity text not null,
  variety text not null default 'UNKNOWN',
  price_unit text,
  arrival_unit text,
  arrivals numeric,
  min_price numeric,
  max_price numeric,
  modal_price numeric,
  source_row bigint,
  created_at timestamptz not null default now()
);

create index if not exists market_data_date_idx on market_data(report_date);
create index if not exists market_data_commodity_idx on market_data(commodity);
create index if not exists market_data_market_idx on market_data(market);
create index if not exists market_data_market_code_idx on market_data(market_code);
create index if not exists market_data_district_idx on market_data(district);
create index if not exists market_data_state_idx on market_data(state);
create index if not exists market_data_target_idx on market_data(commodity, market, variety, report_date);

create table if not exists predictions (
  id text primary key,
  commodity text not null,
  market text not null,
  variety text not null,
  horizon integer not null check (horizon between 1 and 90),
  prediction numeric,
  base_prediction numeric not null,
  reliability numeric not null check (reliability between 0 and 1),
  failure_risk numeric not null check (failure_risk between 0 and 1),
  decision text not null check (decision in ('ACCEPTED', 'ABSTAINED')),
  is_demo boolean not null default false,
  signals jsonb not null,
  reasons jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists predictions_created_idx on predictions(created_at desc);
create index if not exists predictions_commodity_market_idx on predictions(commodity, market);

create table if not exists prediction_outcomes (
  id bigserial primary key,
  prediction_id text not null references predictions(id) on delete cascade,
  actual numeric not null,
  observed_at timestamptz not null default now()
);
create index if not exists outcomes_prediction_idx on prediction_outcomes(prediction_id);

create table if not exists failure_memory (
  id text primary key,
  prediction_id text not null references predictions(id) on delete cascade,
  event_date timestamptz not null,
  commodity text not null,
  market text not null,
  variety text not null,
  prediction numeric,
  actual numeric not null,
  absolute_error numeric not null,
  relative_error numeric not null,
  failure_threshold numeric not null default 0.25,
  severity text not null check (severity in ('NORMAL', 'MODERATE', 'SIGNIFICANT', 'HIGH')),
  reliability numeric not null,
  uncertainty jsonb,
  novelty_score numeric not null default 0,
  drift_score numeric not null default 0,
  context jsonb not null default '{}'::jsonb
);
create index if not exists failure_memory_date_idx on failure_memory(event_date desc);
create index if not exists failure_memory_prediction_idx on failure_memory(prediction_id);
create index if not exists failure_memory_context_idx on failure_memory(commodity, market, variety);

create table if not exists uncertainty_assessments (
  id bigserial primary key,
  prediction_id text not null references predictions(id) on delete cascade,
  model_uncertainty numeric not null,
  historical_failure_risk numeric not null,
  novelty_score numeric not null,
  drift_score numeric not null,
  missing_information numeric not null,
  context_risk numeric not null,
  calculated_at timestamptz not null default now()
);

create table if not exists drift_assessments (
  id bigserial primary key,
  score numeric,
  status text not null,
  affected_features jsonb not null default '[]'::jsonb,
  detection_date timestamptz not null default now(),
  methodology text not null
);

create table if not exists events (
  id bigserial primary key,
  event_date date,
  event_type text not null,
  status text not null default 'NOT_AVAILABLE',
  source text,
  payload jsonb not null default '{}'::jsonb
);

create table if not exists models (
  id bigserial primary key,
  version text not null unique,
  trained_at timestamptz,
  training_start date,
  training_end date,
  commodity text,
  market text,
  horizon integer,
  features jsonb not null default '[]'::jsonb,
  metrics jsonb,
  artifact_path text,
  status text not null default 'NOT_TRAINED'
);

create table if not exists experiments (
  id bigserial primary key,
  name text not null,
  configuration jsonb not null,
  status text not null default 'NOT_RUN',
  started_at timestamptz,
  completed_at timestamptz
);

create table if not exists experiment_results (
  id bigserial primary key,
  experiment_id bigint not null references experiments(id) on delete cascade,
  metrics jsonb not null,
  coverage numeric,
  selective_risk numeric,
  failure_detection_rate numeric,
  calibration numeric,
  created_at timestamptz not null default now()
);

create table if not exists system_metrics (
  id bigserial primary key,
  metric_name text not null,
  metric_value numeric,
  dimensions jsonb not null default '{}'::jsonb,
  recorded_at timestamptz not null default now()
);