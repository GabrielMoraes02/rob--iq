-- Aplicado remotamente via MCP. Apenas registros futuros; não importa CSVs.
create table public.bot_historico (
    sequencia bigint generated always as identity primary key,
    conta text not null check (conta ~ '^[1-9][0-9]*$'),
    ambiente text not null default 'PRACTICE' check (ambiente = 'PRACTICE'),
    id text not null check (length(id) between 1 and 100),
    tipo text not null check (tipo in ('evento', 'resultado')),
    dados jsonb not null check (jsonb_typeof(dados) = 'object'),
    ocorrido_em timestamptz not null,
    recebido_em timestamptz not null default now(),
    unique (conta, ambiente, id)
);
create index bot_historico_conta_sequencia on public.bot_historico (conta, ambiente, sequencia);
alter table public.bot_historico enable row level security;
-- Clientes não acessam a tabela diretamente. A Edge Function autentica a
-- sessão na corretora e usa a conta retornada por ela, nunca uma conta livre.
revoke all on public.bot_historico from public, anon, authenticated;
revoke all on sequence public.bot_historico_sequencia_seq from public, anon, authenticated;
revoke all on public.bot_historico from service_role;
revoke all on sequence public.bot_historico_sequencia_seq from service_role;
grant select, insert on public.bot_historico to service_role;
grant usage, select on sequence public.bot_historico_sequencia_seq to service_role;

