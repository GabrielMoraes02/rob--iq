// A sessão IQ Option é usada apenas durante a requisição: nunca gravar/logar.
const responder = (status: number, body: unknown) => new Response(JSON.stringify(body), {
  status, headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' },
});

async function identificar(ssid: string): Promise<string> {
  // Endpoint fixo: nenhum URL/cookie/ID de usuário fornecido pelo cliente é confiado.
  const resposta = await fetch('https://iqoption.com/api/getprofile', {
    headers: { Cookie: `ssid=${ssid}`, Accept: 'application/json' },
    redirect: 'error', signal: AbortSignal.timeout(10000),
  });
  if (!resposta.ok) throw new Error('auth');
  const perfil = await resposta.json();
  const id = perfil?.result?.user_id ?? perfil?.result?.id;
  if (perfil?.isSuccessful !== true || !/^[1-9][0-9]*$/.test(String(id))) throw new Error('auth');
  return String(id);
}

export async function handler(req: Request): Promise<Response> {
  if (req.method !== 'POST') return responder(405, { erro: 'metodo' });
  let entrada;
  try {
    const texto = await req.text();
    if (new TextEncoder().encode(texto).length > 524288) return responder(413, { erro: 'limite' });
    entrada = JSON.parse(texto);
  } catch { return responder(400, { erro: 'json' }); }
  if (typeof entrada.ssid !== 'string' || !/^[A-Za-z0-9_-]{16,256}$/.test(entrada.ssid))
    return responder(401, { erro: 'sessao' });
  let conta: string;
  try { conta = await identificar(entrada.ssid); }
  catch { return responder(401, { erro: 'sessao_nao_confirmada' }); }
  if (entrada.conta !== conta) return responder(403, { erro: 'conta' });
  const registros = entrada.registros ?? [];
  const apos = entrada.apos ?? 0;
  if (!Array.isArray(registros) || registros.length > 200 || !Number.isSafeInteger(apos) || apos < 0)
    return responder(400, { erro: 'lote' });
  for (const r of registros) {
    if (typeof r.id !== 'string' || r.id.length < 1 || r.id.length > 100 ||
        !['evento', 'resultado'].includes(r.tipo) || !r.dados || Array.isArray(r.dados) ||
        typeof r.dados !== 'object' || typeof r.ocorrido_em !== 'string' ||
        !Number.isFinite(Date.parse(r.ocorrido_em))) return responder(400, { erro: 'registro' });
    const campos = r.tipo === 'evento' ? ['DATA_HORA', 'ATIVO', 'EVENTO', 'DETALHE']
      : ['DATA_HORA', 'ATIVO', 'DIRECAO', 'ID_ORDEM', 'RESULTADO', 'LUCRO_LIQUIDO'];
    if (Object.keys(r.dados).some(k => !campos.includes(k)) || campos.some(k => typeof r.dados[k] !== 'string') ||
        JSON.stringify(r.dados).length > 12000 || !/^\d{2}\/\d{2}\/\d{4} \d{2}:\d{2}:\d{2}$/.test(r.dados.DATA_HORA))
      return responder(400, { erro: 'campos' });
    if (r.tipo === 'resultado' && (!['WIN', 'LOSS', 'EMPATE'].includes(r.dados.RESULTADO) ||
        !Number.isFinite(Number(r.dados.LUCRO_LIQUIDO)) || r.id !== `resultado:${r.dados.ID_ORDEM}`))
      return responder(400, { erro: 'resultado' });
  }
  const url = Deno.env.get('SUPABASE_URL');
  const chave = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY');
  if (!url || !chave) return responder(503, { erro: 'configuracao' });
  const headers = { apikey: chave, Authorization: `Bearer ${chave}`, 'Content-Type': 'application/json' };
  try {
    if (registros.length) {
      const envio = await fetch(`${url}/rest/v1/bot_historico?on_conflict=conta,ambiente,id`, {
        method: 'POST', headers: { ...headers, Prefer: 'resolution=ignore-duplicates,return=minimal' },
        body: JSON.stringify(registros.map(r => ({ conta, ambiente: 'PRACTICE', id: r.id,
          tipo: r.tipo, dados: r.dados, ocorrido_em: r.ocorrido_em }))), signal: AbortSignal.timeout(10000),
      });
      if (!envio.ok) return responder(503, { erro: 'gravar' });
    }
    const consulta = new URL(`${url}/rest/v1/bot_historico`);
    Object.entries({ conta: `eq.${conta}`, ambiente: 'eq.PRACTICE', sequencia: `gt.${apos}`,
      select: 'sequencia,id,tipo,dados,ocorrido_em', order: 'sequencia.asc', limit: '500' })
      .forEach(([k, v]) => consulta.searchParams.set(k, v));
    const leitura = await fetch(consulta, { headers, signal: AbortSignal.timeout(10000) });
    if (!leitura.ok) return responder(503, { erro: 'ler' });
    const recebidos = await leitura.json();
    return responder(200, { conta, registros: recebidos, mais: recebidos.length === 500 });
  } catch { return responder(503, { erro: 'nuvem' }); }
}

Deno.serve(handler);
