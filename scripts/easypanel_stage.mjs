// Deliberately scoped deployment helper. Never print raw Easypanel responses.
// Secrets travel through child-process stdin and live only in Easypanel configuration.
import { spawnSync } from 'node:child_process';
import { createHash, randomBytes, randomUUID } from 'node:crypto';
import https from 'node:https';
import { readFileSync } from 'node:fs';

const project = 'proy1-credito-riesgo';
const backend = 'davidrodriguez2712/nicheradar-backend@sha256:c2d0fd20fbcc16e187226a3664998fdf82254187ed8a35f963eb2a2e3f5da0cb';
const dashboard = 'davidrodriguez2712/nicheradar-dashboard@sha256:913bdff55ed176982dba9fe7063dffc2491ce4377bf93179298e9cfceb5762c5';
const monitoringBackend = 'davidrodriguez2712/nicheradar-backend@sha256:52ff3b77da6052538f8196d5b6ecddf5bd86cc72a8d8e4ae3e98996b67f3e058';
const monitoringDashboard = 'davidrodriguez2712/nicheradar-dashboard@sha256:be8bb601d16b2256f91a57b78398d3aab7a321e4f899629cd9b1c924e8ef050a';
const pilotBackend = 'davidrodriguez2712/nicheradar-backend@sha256:2496fc5a70f994bb180fdfd10e32a7126e129f520d6c232a0dea54c5b39017b7';
const pilotDashboard = 'davidrodriguez2712/nicheradar-dashboard@sha256:7e7c719946f1665ebee77e3176e3656e0d3af0adbbed6520f04d10fd289a95da';
const qualityBackend = 'davidrodriguez2712/nicheradar-backend@sha256:1621b6a6a86ae98603e8f95f1a8b9650dd11a8bbba1c39c2d46ce66f095edcae';
const qualityDashboard = 'davidrodriguez2712/nicheradar-dashboard@sha256:8285cee854b75b8db541e1cee43ae4e70211f1f708c381df05fbcfee906b5539';
const calibrationWorker = 'davidrodriguez2712/nicheradar-worker@sha256:dcaea3e95b4833744d8f7567b9f50fc1b90e5b9e429ddd1661212949a54ab3d7';
const semanticBackend = 'davidrodriguez2712/nicheradar-backend@sha256:7956bfeb7a79699be1aad190694aa102f70c03dfc1fc38f50638f506e0a16db3';
const semanticWorker = 'davidrodriguez2712/nicheradar-worker@sha256:dcaea3e95b4833744d8f7567b9f50fc1b90e5b9e429ddd1661212949a54ab3d7';
const semanticDashboard = 'davidrodriguez2712/nicheradar-dashboard@sha256:e9c0102ee045c657039af8e1ad3c6523fa3f0da693675d390592bebbb9f1a5f2';
const youtubeBackend = 'davidrodriguez2712/nicheradar-backend@sha256:f28455b232de9d09ef3c75da794f2051f5dba826f6bfcda753d4bef240e96ece';
const youtubeWorker = 'davidrodriguez2712/nicheradar-worker@sha256:e1691c99dbe03c368b152dcf42acbaf536043a3e540db71c957f696d69832c55';
const youtubeDashboard = 'davidrodriguez2712/nicheradar-dashboard@sha256:a51fe2009e7ef00610fc1f3d9d6a7c48e94beeaeb5ff6f33d30211499f37c23d';
const dashboardFixBackend = 'davidrodriguez2712/nicheradar-backend@sha256:8147d15d847f8eb8b3f08e0265160b0d81964a3c71910dccd3142704dc10bc07';
const dashboardFixWorker = 'davidrodriguez2712/nicheradar-worker@sha256:ee73759117312bd2d7779b77827963822e410721ec1bc35dcb3a13d022db1c86';
const dashboardFixDashboard = 'davidrodriguez2712/nicheradar-dashboard@sha256:2f377d7a355db2a17172569935c2620a0a5587bd7a85f3ee5fb717ec75a9ca66';
const uiRedesignBackend = 'davidrodriguez2712/nicheradar-backend@sha256:565321bdb90be0dce161f5aaff096d0b86c2b594cb0989cc6f958fc16416d133';
const uiRedesignWorker = 'davidrodriguez2712/nicheradar-worker@sha256:a6d0de667e142f65f63554c3a738a2d05850e9a04f15f53dad977abf499dc08d';
const uiRedesignDashboard = 'davidrodriguez2712/nicheradar-dashboard@sha256:7407cbf9a434fe37cef3ef02048a8227725a52f0b915fcc1a823bb429adcdc55';
const jsonCleanupBackend = 'davidrodriguez2712/nicheradar-backend@sha256:46869c13afa1aed230459d7f8a6f7df3347bcc038ccea97bdd3f20bfb9ac66a0';
const jsonCleanupWorker = 'davidrodriguez2712/nicheradar-worker@sha256:46a5f466917a3807f61ace8525e885fd64739fef0ee893caab76073f0a950fd1';
const jsonCleanupDashboard = 'davidrodriguez2712/nicheradar-dashboard@sha256:cc04f2b3389291ef100cda5cc4223d4cad31364af2c8ff055b49232ef55a9a9e';
const defaultRecipeBackend = 'davidrodriguez2712/nicheradar-backend@sha256:b73d984c3d6c46b9b0395f7e5e9d8020ac4661778a2ce368a8b5bb27986e51d2';
const defaultRecipeWorker = 'davidrodriguez2712/nicheradar-worker@sha256:e963e60197ea51850b3cee8015d2833cdf1e06329a7911622e03390ec5bc1d3b';
const defaultRecipeDashboard = 'davidrodriguez2712/nicheradar-dashboard@sha256:0f39d08b345f3fbd53318cad2c85216541dcfe35b22878d365de45467ed4462f';
const homeProfitBackend = 'davidrodriguez2712/nicheradar-backend@sha256:5b199af90c670649cb1856119abc01312abb07b2bf991b0624f478c68a759e19';
const homeProfitWorker = 'davidrodriguez2712/nicheradar-worker@sha256:377b7750a89511115e0e1a8fe6d852b7581c4587fec5ba651a513c0f323d43eb';
const homeProfitDashboard = 'davidrodriguez2712/nicheradar-dashboard@sha256:503ca3e018a671d4133321c9cefd110120d825843861dfaa9e157aa648ba34e0';
const channelAnalysisBackend = 'davidrodriguez2712/nicheradar-backend@sha256:6853852ef827b744c4859adf2d33314fc6b9ecb922ff825b10fc019475359956';
const channelAnalysisWorker = 'davidrodriguez2712/nicheradar-worker@sha256:56d8e017f4967bde96eed8f1178ea4af24c164e343a4b0bca7e89c1773d18972';
const channelAnalysisDashboard = 'davidrodriguez2712/nicheradar-dashboard@sha256:9467acfa7849ef4ea45a2767f1e5f1cfe859a259f19d6321e1fdee30e3f587c3';
const insightsScoreBackend = 'davidrodriguez2712/nicheradar-backend@sha256:8d2ed4997c5f0cd80d3427c36cc65b54a2a174847c3c7dbf243c4d2021a2223b';
const insightsScoreWorker = 'davidrodriguez2712/nicheradar-worker@sha256:84173a9da7bbd7f106b56a0b2187f49b60c554090f9b930f343a64c189e5c780';
const insightsScoreDashboard = 'davidrodriguez2712/nicheradar-dashboard@sha256:81244accb27f77b7456abfc4d68fffc2e46b5393a5f8a524aa16783e2bcc1cfe';
const batchSizeCrashFixBackend = 'davidrodriguez2712/nicheradar-backend@sha256:dc3b1c10066bf1a10aa30adf5b9e9f32f9300801a825b50f4198e745218aa6b6';
const batchSizeCrashFixWorker = 'davidrodriguez2712/nicheradar-worker@sha256:d93066845bd95efdd187333c02fba7e2026957e8a6c65e194dfda0be51eefbdd';
const batchSizeCrashFixDashboard = 'davidrodriguez2712/nicheradar-dashboard@sha256:94f028e561f89943d6f1cd3c7110d089159a04612838580578b9020751d4335f';
const marketFlowBackend = 'davidrodriguez2712/nicheradar-backend@sha256:f3907cd6041c0992b826a5bfa022eb4e9684a596f975568878dc24756756103c';
const marketFlowWorker = 'davidrodriguez2712/nicheradar-worker@sha256:afdea300c1ca70fe6691450a2a66d083bd0e07e4bad425cab1e188a1c1efa14e';
const marketFlowDashboard = 'davidrodriguez2712/nicheradar-dashboard@sha256:d7d3313cddc6cb6b4df1d2648bac095545e907d90c6738816a12c22af18a9f03';
const postgres = 'postgres:18@sha256:4ef4dbc939d61acea57712655ddb4b4ab27419c913f94cca0cd57cb3ea3c2280';
const pilotsBackend = 'davidrodriguez2712/nicheradar-backend@sha256:edadc0f750b3058e26a24cbbcee963532f3c75d14789aea9858fa57540b17d08';
const pilotsWorker = 'davidrodriguez2712/nicheradar-worker@sha256:b911bdbeda0d325f71e4295cea7b1d331bd9b2c0945cb91d9f48cd0000e92536';
const pilotsDashboard = 'davidrodriguez2712/nicheradar-dashboard@sha256:8d9d036b8604eede928423ce55397f73d9a710d1fb18063fcbeb5dceed405351';
const languageBackend = 'davidrodriguez2712/nicheradar-backend@sha256:0a80040ce82ec24429f23f128ea838e68947e5399b2e21cb15dbde847bd26e73';
const languageWorker = 'davidrodriguez2712/nicheradar-worker@sha256:d7f2ec263467545cf1e1ae70a3af54d25cd29b6a8daf48a7b566fb91dc8480b7';
const languageDashboard = 'davidrodriguez2712/nicheradar-dashboard@sha256:c889d5fa5a16ce7614c33aeb6d2287cd777479b4a44932477049b498dd72fadd';
const stopRulesBackend = 'davidrodriguez2712/nicheradar-backend@sha256:8f437decfea1f89a38e0e570cf68efa5804f99c873b77277bc173c78d8541366';
const stopRulesWorker = 'davidrodriguez2712/nicheradar-worker@sha256:e66e49927a35b03945f34bf8cb064a35bfb6acdf5b364269e1d09a8f0322aaf0';
const stopRulesDashboard = 'davidrodriguez2712/nicheradar-dashboard@sha256:70ba90d5f7ae56f816ecda1fbc86f9c81c54c6e4a1fc829092a4a71cee5c3202';
const shortsReportBackend = 'davidrodriguez2712/nicheradar-backend@sha256:d0e5e1a6fd6053006866394e6404a59e87c46f308e95691f55b24b1e025e3372';
const shortsReportWorker = 'davidrodriguez2712/nicheradar-worker@sha256:76914e257c87df3944ba3b4ee65fd476d2166bc772edc35d9a294b8e42c15edc';
const shortsReportDashboard = 'davidrodriguez2712/nicheradar-dashboard@sha256:fe0c627c3aa6b9b7bfa3107433a623457c25c3041ee7c3aeeef79e76aa860017';
const gatesBackend = 'davidrodriguez2712/nicheradar-backend@sha256:6cbe74615cfe097dcd09be5abb80e336eff9f251fb1975fe172d9737f70040d9';
const gatesWorker = 'davidrodriguez2712/nicheradar-worker@sha256:b647cf4bbe2a0be0e7d5d652e6148de846968ba1ed4a1ac5f95e213faa9a961e';
const gatesDashboard = 'davidrodriguez2712/nicheradar-dashboard@sha256:7cb948776289acd27f40dd00e5ee65b07124ca94fc092fa9bf7e965496692be0';
const batchBackend = 'davidrodriguez2712/nicheradar-backend@sha256:6678ad1227d6de0f266f5e4145784b018230da93e5089cd7af7e1e5407e3e5e2';
const batchWorker = 'davidrodriguez2712/nicheradar-worker@sha256:3961e6681f57c68c8f85778e3d26fd4286fb34ad2515678ed6b81005040ff0fc';
const batchDashboard = 'davidrodriguez2712/nicheradar-dashboard@sha256:53e92317c3783474ec0acbdcb5340c93ef830fc29d9d42563273035dd7cff9a1';
const classifyBackend = 'davidrodriguez2712/nicheradar-backend@sha256:5b0b2d30f464644d9ae816bb0f2565e9fde049be01af033db30f7a91c32cc733';
const classifyWorker = 'davidrodriguez2712/nicheradar-worker@sha256:766f98011e8bdce7a3f9406508806d34b05a24fbc388cd2b33f5d41986c4909e';
const classifyDashboard = 'davidrodriguez2712/nicheradar-dashboard@sha256:d8ab255db72b512f591c87342ddc12b4359d5f805458a8f240550646ba3beabc';
const enrichBackend = 'davidrodriguez2712/nicheradar-backend@sha256:9004772ee6e2e13febbb881771be3e87ad9822305130830afe4127fbd09261b7';
const enrichWorker = 'davidrodriguez2712/nicheradar-worker@sha256:825d92086e70b2c5c6e3edba92de022e40d727c19d3f7d4d0ca8921728e05ebd';
const enrichDashboard = 'davidrodriguez2712/nicheradar-dashboard@sha256:dcfc794bab0d95fc46eae6971b3cfe3291d23de358f9864ad90ed37d2714a29d';
const enrichFixBackend = 'davidrodriguez2712/nicheradar-backend@sha256:6bf0c40f1387e7193baa031f7ba31a668f77217d62cdb2c4399f5e994038fc6b';
const enrichFixWorker = 'davidrodriguez2712/nicheradar-worker@sha256:ecb1c8beda9d1cd571054340440730f10e5071221ba77fc5544ab58ccc84c417';
const enrichFixDashboard = 'davidrodriguez2712/nicheradar-dashboard@sha256:971abbd663183d8ce51c6dca65130899b407ea12ab1b3c8fc84562ff7758d121';
const evidenceBackend = 'davidrodriguez2712/nicheradar-backend@sha256:46622f22b78fc8c8b870dc24f91b9713c3dbbbb86f3d3aafc48950b6c4b4d4e0';
const evidenceWorker = 'davidrodriguez2712/nicheradar-worker@sha256:e6e0ad8bdcf4dac45b01854094a7ed60ecd57283224dc03c6bd393affe4184d6';
const evidenceDashboard = 'davidrodriguez2712/nicheradar-dashboard@sha256:1a0c243752c45000c8f703dfe78abcc36243fda3898fa0be37074a2cc9394baa';
const evidenceFixBackend = 'davidrodriguez2712/nicheradar-backend@sha256:2dfc631c7085796b90fded1ccc1fd2cbb34b05da481da4291af38a0ab4bc9256';
const evidenceFixWorker = 'davidrodriguez2712/nicheradar-worker@sha256:ee89f6020ea8923870a8b70e55e3d663f596d8958a45dde006babbf9c9c804e2';
const evidenceFixDashboard = 'davidrodriguez2712/nicheradar-dashboard@sha256:9f7113905334f28a96a646895a12684a3488edaba3016685a48a8e164640e443';
const evidenceTolBackend = 'davidrodriguez2712/nicheradar-backend@sha256:92b84bc1ad9df4acea7e8b6731d72b5be025de2a8168a0e34ef2d9370ed8f2bc';
const evidenceTolWorker = 'davidrodriguez2712/nicheradar-worker@sha256:c8d313f0cb847a09d28599a7d0f1fdaa5e6d5a62016395c395d075c403b51069';
const evidenceTolDashboard = 'davidrodriguez2712/nicheradar-dashboard@sha256:a8cfd4fa5b5683ba3568f01ab4bf736ee3545b870f80041c9438823fc838f6c4';
const evidenceRelBackend = 'davidrodriguez2712/nicheradar-backend@sha256:191d8366a1536117de1df1b0cf29c227f72f24524d33938895196c5f54726238';
const evidenceRelWorker = 'davidrodriguez2712/nicheradar-worker@sha256:27fd180ac8e8b535db4f02905a21a34680c57c556ba6a7d3dc816f2a637f19f5';
const evidenceRelDashboard = 'davidrodriguez2712/nicheradar-dashboard@sha256:fb6640cce62649f660f8d92834923c55d26148fdc57d3b4bd8451dbd33d9f786';
const evidenceNotesBackend = 'davidrodriguez2712/nicheradar-backend@sha256:7de141b2df4cc26debc83cfaa562f55b40360a16a939f12a84b50650a2bf6682';
const evidenceNotesWorker = 'davidrodriguez2712/nicheradar-worker@sha256:0eadf8f9925fd466a73ac4c3f5e0db33e3d0b9ed65d7ed6f5f94c989de3753d6';
const evidenceNotesDashboard = 'davidrodriguez2712/nicheradar-dashboard@sha256:3a4012c2bbbf52ed5b5f7c0949d19166bde9bd9fb3dae49b5ec6cb104f1a3635';
const evidenceDollarBackend = 'davidrodriguez2712/nicheradar-backend@sha256:369df9cd5796587a7384fe85cec61878f3c368bec86db4ed4db596872233f2c7';
const evidenceDollarWorker = 'davidrodriguez2712/nicheradar-worker@sha256:d243b991603c66c362dea4480dda50d2b62bfe5f5cb90ccf4e0551fd49fbf563';
const evidenceDollarDashboard = 'davidrodriguez2712/nicheradar-dashboard@sha256:f3361dbbadfd8f3d8325de6db7449187e3e408480baf5afcec653a2dd0796484';
const evidenceRpmBackend = 'davidrodriguez2712/nicheradar-backend@sha256:bd16461c98b4c1ded9232d403b9c3118704142283d132b3a6d84978390573eec';
const evidenceRpmWorker = 'davidrodriguez2712/nicheradar-worker@sha256:0f51b3f944acab022a879c8087fb1116aaedc01187f09236a1661663bd4ed06a';
const evidenceRpmDashboard = 'davidrodriguez2712/nicheradar-dashboard@sha256:9b95d66c4e2eebb775c5ce7b9f747922fdfd066651a72d411847a2ac08d519b8';
const qualityRpmBackend = 'davidrodriguez2712/nicheradar-backend@sha256:5af1f9386cd6ef39a3c94cd6c77317958234e724b75c6ec64e8a39b22342e215';
const qualityRpmWorker = 'davidrodriguez2712/nicheradar-worker@sha256:d4f0b6052115f82ac0e071e6b352810a22b270b295d38e98c2db5ed2f61d99c5';
const qualityRpmDashboard = 'davidrodriguez2712/nicheradar-dashboard@sha256:d2337db8b8415af3f9747896b71083bac19cb03bb3d876b780483eb4fc43f349';
const isolatedIncomeBackend = 'davidrodriguez2712/nicheradar-backend@sha256:04e83051892ad199318a8012862dc0197f0b14e1e073363fcc79f21ca4091e11';
const isolatedIncomeWorker = 'davidrodriguez2712/nicheradar-worker@sha256:3703bf469efcf01bc088d4db9e8a49fce896658d4c65d8633f7a44ba046ec42a';
const isolatedIncomeDashboard = 'davidrodriguez2712/nicheradar-dashboard@sha256:e12841ebb4a68b8c0dade29725c6c8d5076b35150d269455e355128025e3b035';
const subnicheBackend = 'davidrodriguez2712/nicheradar-backend@sha256:899710b33111d54fca314bba2a3fee915148d3c732142a515797ce37f5f86fb3';
const subnicheWorker = 'davidrodriguez2712/nicheradar-worker@sha256:f1032b66c7cb9ece7a08ce6ef9f83acc4c548381d55521e70318ac4305ed09ac';
const subnicheDashboard = 'davidrodriguez2712/nicheradar-dashboard@sha256:040f4df0d79f1169e8d03526c926a21b9eece3739e30c8958401a063b4eac358';
const names = ['nicheradar-db', 'nicheradar-api', 'nicheradar-worker', 'nicheradar-dashboard'];
const secret = () => randomBytes(32).toString('hex');
const resources = (cpu) => ({memoryLimit:512,memoryReservation:128,cpuLimit:cpu,cpuReservation:0.1});
const sshArgs=['-i','/Users/davidrodriguez/.ssh/id_ed25519','-o','IdentitiesOnly=yes',
  '-o','BatchMode=yes','-o','ConnectTimeout=10','-o','StrictHostKeyChecking=yes','root@194.61.28.253'];
const quote=s=>`'${s.replaceAll("'", "'\\''")}'`;

function cli(args, input, secrets = false) {
  const flags = ['--server','contabo','--format','json'];
  if (secrets) flags.push('--show-secrets');
  const result = spawnSync('easypanel', [...flags,...args,...(input ? ['--input','-'] : [])], {
    input: input ? JSON.stringify(input) : undefined, encoding:'utf8', timeout:45000,
    maxBuffer:4*1024*1024,
  });
  if (result.error || result.status !== 0) throw new Error(`CLI ${args.slice(0,2).join(' ')} failed (exit ${result.status}); response withheld`);
  try { return JSON.parse(result.stdout); }
  catch { throw new Error('CLI returned non-JSON; response withheld'); }
}

function inventory() {
  return cli(['projects','inspect',project]).services.map(s => ({name:s.name,type:s.type,enabled:s.enabled}));
}

function summarize(kind, name) {
  const s = cli([kind,'inspect',`${project}/${name}`]);
  console.log(JSON.stringify({name:s.name,type:s.type,enabled:s.enabled,image:s.image ?? s.source?.image,
    resources:s.resources,deploy:s.deploy,ports:s.ports,exposedPort:s.exposedPort,
    mounts:(s.mounts ?? []).map(m=>({type:m.type,mountPath:m.mountPath})),
    domains:(s.domains ?? []).map(d=>({host:d.host,port:d.port,https:d.https})),
    basicAuthConfigured:(s.basicAuth?.length ?? 0)>0,
    pgWebEnabled:s.pgWeb?.enabled,dbGateEnabled:s.dbGate?.enabled}));
}

function dbURL() {
  const s = cli(['postgres','inspect',`${project}/nicheradar-db`],undefined,true);
  if(s.name!=='nicheradar-db' || s.databaseName!=='nicheradar' || !s.password || s.password==='[REDACTED]') throw new Error('Unexpected database configuration');
  return `postgresql+psycopg://${encodeURIComponent(s.user)}:${encodeURIComponent(s.password)}@${project}_nicheradar-db:5432/nicheradar`;
}

function appEnv(name) {
  const s=cli(['app','inspect',`${project}/${name}`],undefined,true);
  if(s.name!==name || !s.env || s.env==='[REDACTED]') throw new Error('App environment unavailable');
  return Object.fromEntries(s.env.split('\n').filter(Boolean).map(line=>{const i=line.indexOf('=');return [line.slice(0,i),line.slice(i+1)];}));
}

function localVidIQToken() {
  const lines=readFileSync(new URL('../.env',import.meta.url),'utf8').split(/\r?\n/);
  const matches=lines.filter(line=>line.startsWith('NR_VIDIQ_TOKEN='));
  if(matches.length!==1) throw new Error('Exactly one local NR_VIDIQ_TOKEN is required');
  const token=matches[0].slice('NR_VIDIQ_TOKEN='.length);
  if(!token || /\s/.test(token)) throw new Error('Invalid local vidIQ token');
  return token;
}

function localAnthropicKey() {
  const lines=readFileSync(new URL('../.env',import.meta.url),'utf8').split(/\r?\n/);
  const matches=lines.filter(line=>line.startsWith('NR_ANTHROPIC_API_KEY='));
  if(matches.length!==1) throw new Error('Exactly one local NR_ANTHROPIC_API_KEY is required');
  const key=matches[0].slice('NR_ANTHROPIC_API_KEY='.length);
  if(!key || /\s/.test(key)) throw new Error('Invalid local Anthropic key');
  return key;
}

function localYouTubeConfig() {
  const lines=readFileSync(new URL('../.env',import.meta.url),'utf8').split(/\r?\n/);
  const values=Object.fromEntries(lines.filter(line=>line.startsWith('NR_YOUTUBE_')).map(line=>{
    const i=line.indexOf('='); return [line.slice(0,i),line.slice(i+1)];
  }));
  const required=['NR_YOUTUBE_API_KEY','NR_YOUTUBE_AUTH_SCOPE','NR_YOUTUBE_CONNECTION_VALIDATED_AT',
    'NR_YOUTUBE_QUOTA_PER_RUN','NR_YOUTUBE_QUOTA_PER_WEEK','NR_YOUTUBE_QUOTA_PER_MONTH',
    'NR_YOUTUBE_MAXIMUM_VIDEOS'];
  if(required.some(key=>!values[key])) throw new Error('Complete YouTube configuration is required in private .env');
  if(/\s/.test(values.NR_YOUTUBE_API_KEY) || !/^[A-Za-z0-9._:-]{1,120}$/.test(values.NR_YOUTUBE_AUTH_SCOPE))
    throw new Error('Invalid local YouTube credential or scope');
  const validated=Date.parse(values.NR_YOUTUBE_CONNECTION_VALIDATED_AT);
  if(!Number.isFinite(validated) || validated>Date.now()) throw new Error('Invalid YouTube validation date');
  for(const key of required.filter(key=>key.includes('QUOTA_'))) {
    if(!/^[1-9][0-9]*$/.test(values[key])) throw new Error('YouTube quotas must be positive integers');
  }
  if(!/^(?:[1-9]|[1-9][0-9]|1[0-9]{2}|200)$/.test(values.NR_YOUTUBE_MAXIMUM_VIDEOS))
    throw new Error('YouTube maximum videos must be between 1 and 200');
  return {...values,NR_YOUTUBE_LIVE_ENABLED:'true'};
}

function localLLMConfig() {
  const lines=readFileSync(new URL('../.env',import.meta.url),'utf8').split(/\r?\n/);
  const values=Object.fromEntries(lines.filter(line=>line.startsWith('NR_LLM_')).map(line=>{
    const i=line.indexOf('='); return [line.slice(0,i),line.slice(i+1)];
  }));
  const required=['NR_LLM_API_KEY','NR_LLM_CONFIGURATION'];
  if(required.some(key=>!values[key])) throw new Error('Complete LLM configuration is required in private .env');
  if(/\s/.test(values.NR_LLM_API_KEY)) throw new Error('Invalid local LLM credential');
  let configuration;
  try { configuration=JSON.parse(values.NR_LLM_CONFIGURATION); }
  catch { throw new Error('NR_LLM_CONFIGURATION is not valid JSON'); }
  if(!configuration.tariff?.model || !configuration.tariff?.verified_at || !configuration.tariff?.valid_until)
    throw new Error('NR_LLM_CONFIGURATION is missing required tariff fields');
  if(Date.parse(configuration.tariff.valid_until)<=Date.now()) throw new Error('LLM tariff is no longer valid');
  return {NR_LLM_API_KEY:values.NR_LLM_API_KEY,NR_LLM_CONFIGURATION:values.NR_LLM_CONFIGURATION,NR_LLM_ENABLED:'true'};
}

async function publicProbe() {
  const host='nicheradar.soydavidrodriguez.com';
  const s=cli(['app','inspect',`${project}/nicheradar-dashboard`],undefined,true);
  if(s.name!=='nicheradar-dashboard' || s.basicAuth?.length!==1 ||
    s.basicAuth[0].username!=='david' || !s.basicAuth[0].password ||
    s.basicAuth[0].password==='[REDACTED]') throw new Error('Proxy credentials unavailable');
  const auth='Basic '+Buffer.from(`david:${s.basicAuth[0].password}`).toString('base64');
  const request=(path, authorization, websocket=false)=>new Promise((resolve,reject)=>{
    const key=randomBytes(16).toString('base64');
    const headers={...(authorization?{Authorization:authorization}:{}),...(websocket?{
      Connection:'Upgrade',Upgrade:'websocket','Sec-WebSocket-Version':'13',
      'Sec-WebSocket-Key':key,'Sec-WebSocket-Protocol':'streamlit',Origin:`https://${host}`}: {})};
    // Bypass stale local DNS, never TLS verification: the hostname/SNI stays intact.
    const req=https.request({hostname:host,servername:host,port:443,path,headers,
      lookup:(_hostname,options,callback)=>options.all
        ? callback(null,[{address:'194.61.28.253',family:4}])
        : callback(null,'194.61.28.253',4),
      agent:false,timeout:15000,rejectUnauthorized:true},res=>{
      res.resume(); resolve({status:res.statusCode});
    });
    req.on('upgrade',(res,socket)=>{
      const accepted=createHash('sha1').update(key+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest('base64');
      const valid=res.headers['sec-websocket-accept']===accepted && res.headers['sec-websocket-protocol']==='streamlit';
      socket.destroy(); resolve({status:res.statusCode,websocketValid:valid});
    });
    req.on('timeout',()=>req.destroy(new Error('Probe timeout')));
    req.on('error',()=>reject(new Error('Public HTTPS probe failed; details withheld')));
    req.end();
  });
  for(const path of ['/','/_stcore/health','/_stcore/stream']) {
    const r=await request(path,undefined,path.endsWith('/stream'));
    if(r.status!==401) throw new Error('Anonymous proxy protection failed');
  }
  if((await request('/','Basic '+Buffer.from('david:incorrect-password').toString('base64'))).status!==401)
    throw new Error('Invalid proxy password was not rejected');
  for(const path of ['/','/_stcore/health']) {
    if((await request(path,auth)).status!==200) throw new Error('Authenticated HTTPS failed');
  }
  const ws=await request('/_stcore/stream',auth,true);
  if(ws.status!==101 || !ws.websocketValid) throw new Error('Authenticated WebSocket handshake failed');
  console.log('public_https_verified anonymous_and_invalid_auth_denied authenticated_http_ok websocket_upgrade_verified');
}

const action=process.argv[2];
try {
  if(action==='public-probe') {
    await publicProbe();
  } else if(action==='inspect') {
    const services=inventory(); console.log(JSON.stringify({project,services}));
    for(const s of services.filter(s=>names.includes(s.name))) summarize(s.type,s.name);
  } else if(action==='deploy-monitoring') {
    const name=process.argv[3];
    if(!names.slice(1).includes(name)) throw new Error('Only NicheRadar apps can be updated');
    const isDashboard=name==='nicheradar-dashboard';
    const before=cli(['app','inspect',`${project}/${name}`]);
    const env=appEnv(name);
    if(before.source?.image!==(isDashboard?dashboard:backend) || before.ports?.length ||
       before.deploy?.replicas!==1 || before.resources?.memoryLimit!==512 ||
       env.NR_MODE!=='synthetic' || env.NR_RADAR_PAUSED!=='true' ||
       env.NR_VIDIQ_TOKEN || env.NR_YOUTUBE_API_KEY || env.NR_LLM_API_KEY ||
       (isDashboard && !before.basicAuth?.length)) throw new Error('Release preconditions failed');
    const image=isDashboard?monitoringDashboard:monitoringBackend;
    cli(['app','update-source-image',`${project}/${name}`,'--yes'],{image});
    const after=cli(['app','inspect',`${project}/${name}`]);
    for(const field of ['env','resources','deploy','ports','mounts','basicAuth']) {
      if(JSON.stringify(before[field])!==JSON.stringify(after[field])) throw new Error('Unexpected configuration change; deployment not requested');
    }
    if(after.source?.image!==image) throw new Error('Image setting not persisted');
    cli(['app','deploy',`${project}/${name}`,'--yes']);
    console.log(JSON.stringify({name,image,deployRequested:true}));
  } else if(action==='deploy-pilot-code') {
    const name=process.argv[3];
    if(!names.slice(1).includes(name)) throw new Error('Only NicheRadar apps can be updated');
    const isDashboard=name==='nicheradar-dashboard';
    const before=cli(['app','inspect',`${project}/${name}`]);
    const env=appEnv(name);
    if(before.source?.image!==(isDashboard?monitoringDashboard:monitoringBackend) || before.ports?.length ||
       before.deploy?.replicas!==1 || before.resources?.memoryLimit!==512 ||
       env.NR_MODE!=='synthetic' || env.NR_RADAR_PAUSED!=='true' ||
       env.NR_VIDIQ_TOKEN || env.NR_YOUTUBE_API_KEY || env.NR_LLM_API_KEY ||
       (isDashboard && !before.basicAuth?.length)) throw new Error('Pilot code release preconditions failed');
    const image=isDashboard?pilotDashboard:pilotBackend;
    cli(['app','update-source-image',`${project}/${name}`,'--yes'],{image});
    const after=cli(['app','inspect',`${project}/${name}`]);
    for(const field of ['env','resources','deploy','ports','mounts','basicAuth']) {
      if(JSON.stringify(before[field])!==JSON.stringify(after[field])) throw new Error('Unexpected configuration change; deployment not requested');
    }
    if(after.source?.image!==image) throw new Error('Image setting not persisted');
    cli(['app','deploy',`${project}/${name}`,'--yes']);
    console.log(JSON.stringify({name,image,deployRequested:true,mode:'synthetic',paused:true}));
  } else if(action==='configure-live-paused') {
    const token=localVidIQToken();
    for(const name of names.slice(1)) {
      const isDashboard=name==='nicheradar-dashboard';
      const before=cli(['app','inspect',`${project}/${name}`]);
      const env=appEnv(name);
      if(before.source?.image!==(isDashboard?pilotDashboard:pilotBackend) ||
         env.NR_MODE!=='synthetic' || env.NR_RADAR_PAUSED!=='true' || env.NR_VIDIQ_TOKEN)
        throw new Error('Live configuration preconditions failed');
      const next={...env,NR_MODE:'live',NR_RADAR_PAUSED:'true'};
      if(!isDashboard) Object.assign(next,{NR_VIDIQ_TOKEN:token,NR_VIDIQ_AUTH_SCOPE:'personal-primary',
        NR_VIDIQ_CONNECTION_VALIDATED_AT:'2026-09-22T14:02:10Z',
        NR_VIDIQ_CREDIT_CYCLE_STARTED_AT:'2026-09-04T01:49:11.161411Z',
        NR_VIDIQ_LIVE_ENABLED:'true',NR_VIDIQ_PILOT_AUTHORIZED:'true'});
      cli(['app','update-env',`${project}/${name}`,'--yes'],{env:Object.entries(next).map(([k,v])=>`${k}=${v}`).join('\n')});
      const after=cli(['app','inspect',`${project}/${name}`]);
      for(const field of ['source','resources','deploy','ports','mounts','basicAuth']) {
        if(JSON.stringify(before[field])!==JSON.stringify(after[field])) throw new Error('Unexpected non-environment change');
      }
      cli(['app','deploy',`${project}/${name}`,'--yes']);
      console.log(JSON.stringify({name,configured:true,mode:'live',paused:true,providerCredential:isDashboard?false:true}));
    }
  } else if(action==='set-market-caps') {
    // Solo el worker corre el scraper; cambia únicamente dos topes de entorno (decisión 2026-10-27).
    const name='nicheradar-worker';
    const before=cli(['app','inspect',`${project}/${name}`]);
    const env=appEnv(name);
    if(env.NR_MODE!=='live') throw new Error('Market caps preconditions failed');
    const next={...env,NR_MARKET_INTEL_DETAIL_CAP_PER_RUN:'600',NR_MARKET_INTEL_CLASSIFY_CAP_PER_RUN:'500'};
    cli(['app','update-env',`${project}/${name}`,'--yes'],{env:Object.entries(next).map(([k,v])=>`${k}=${v}`).join('\n')});
    const after=cli(['app','inspect',`${project}/${name}`]);
    for(const field of ['source','resources','deploy','ports','mounts','basicAuth']) {
      if(JSON.stringify(before[field])!==JSON.stringify(after[field])) throw new Error('Unexpected non-environment change');
    }
    cli(['app','deploy',`${project}/${name}`,'--yes']);
    console.log(JSON.stringify({name,detailCap:600,classifyCap:500,deployRequested:true}));
  } else if(action==='deploy-quality-code') {
    const name=process.argv[3];
    if(!names.slice(1).includes(name)) throw new Error('Only NicheRadar apps can be updated');
    const isDashboard=name==='nicheradar-dashboard';
    const before=cli(['app','inspect',`${project}/${name}`]);
    const env=appEnv(name);
    if(before.source?.image!==(isDashboard?pilotDashboard:pilotBackend) ||
       env.NR_MODE!=='live' || env.NR_RADAR_PAUSED!=='true' ||
       (!isDashboard && (!env.NR_VIDIQ_TOKEN || env.NR_VIDIQ_LIVE_ENABLED!=='true' || env.NR_VIDIQ_PILOT_AUTHORIZED!=='true')) ||
       (isDashboard && env.NR_VIDIQ_TOKEN)) throw new Error('Quality release preconditions failed');
    const image=isDashboard?qualityDashboard:qualityBackend;
    cli(['app','update-source-image',`${project}/${name}`,'--yes'],{image});
    const after=cli(['app','inspect',`${project}/${name}`]);
    for(const field of ['env','resources','deploy','ports','mounts','basicAuth']) {
      if(JSON.stringify(before[field])!==JSON.stringify(after[field])) throw new Error('Unexpected configuration change; deployment not requested');
    }
    if(after.source?.image!==image) throw new Error('Image setting not persisted');
    cli(['app','deploy',`${project}/${name}`,'--yes']);
    console.log(JSON.stringify({name,image,deployRequested:true,mode:'live',paused:true}));
  } else if(action==='deploy-semantic-code') {
    const name=process.argv[3];
    if(!names.slice(1).includes(name)) throw new Error('Only NicheRadar apps can be updated');
    const isDashboard=name==='nicheradar-dashboard';
    const before=cli(['app','inspect',`${project}/${name}`]);
    const env=appEnv(name);
    const expected=isDashboard?qualityDashboard:qualityBackend;
    if(before.source?.image!==expected || before.ports?.length ||
       before.deploy?.replicas!==1 || before.resources?.memoryLimit!==512 ||
       env.NR_MODE!=='live' || env.NR_RADAR_PAUSED!=='true' ||
       (!isDashboard && (!env.NR_VIDIQ_TOKEN || env.NR_VIDIQ_LIVE_ENABLED!=='true' || env.NR_VIDIQ_PILOT_AUTHORIZED!=='true')) ||
       (isDashboard && env.NR_VIDIQ_TOKEN)) throw new Error('Semantic release preconditions failed');
    const image=isDashboard?semanticDashboard:name==='nicheradar-worker'?semanticWorker:semanticBackend;
    cli(['app','update-source-image',`${project}/${name}`,'--yes'],{image});
    const after=cli(['app','inspect',`${project}/${name}`]);
    for(const field of ['env','resources','deploy','ports','mounts','basicAuth']) {
      if(JSON.stringify(before[field])!==JSON.stringify(after[field])) throw new Error('Unexpected configuration change; deployment not requested');
    }
    if(after.source?.image!==image) throw new Error('Image setting not persisted');
    cli(['app','deploy',`${project}/${name}`,'--yes']);
    console.log(JSON.stringify({name,image,deployRequested:true,mode:'live',paused:true}));
  } else if(action==='deploy-youtube-code') {
    const name=process.argv[3];
    if(!names.slice(1).includes(name)) throw new Error('Only NicheRadar apps can be updated');
    const isDashboard=name==='nicheradar-dashboard';
    const before=cli(['app','inspect',`${project}/${name}`]);
    const env=appEnv(name);
    const expected=isDashboard?semanticDashboard:name==='nicheradar-worker'?semanticWorker:semanticBackend;
    if(before.source?.image!==expected || before.ports?.length ||
       before.deploy?.replicas!==1 || before.resources?.memoryLimit!==512 ||
       env.NR_MODE!=='live' || env.NR_RADAR_PAUSED!=='true' ||
       (!isDashboard && (!env.NR_VIDIQ_TOKEN || env.NR_VIDIQ_LIVE_ENABLED!=='true' || env.NR_VIDIQ_PILOT_AUTHORIZED!=='true')) ||
       (!isDashboard && (env.NR_YOUTUBE_API_KEY || env.NR_YOUTUBE_LIVE_ENABLED==='true')) ||
       (isDashboard && (env.NR_VIDIQ_TOKEN || env.NR_YOUTUBE_API_KEY)))
      throw new Error('YouTube code release preconditions failed');
    const image=isDashboard?youtubeDashboard:name==='nicheradar-worker'?youtubeWorker:youtubeBackend;
    cli(['app','update-source-image',`${project}/${name}`,'--yes'],{image});
    const after=cli(['app','inspect',`${project}/${name}`]);
    for(const field of ['env','resources','deploy','ports','mounts','basicAuth']) {
      if(JSON.stringify(before[field])!==JSON.stringify(after[field])) throw new Error('Unexpected configuration change; deployment not requested');
    }
    if(after.source?.image!==image) throw new Error('Image setting not persisted');
    cli(['app','deploy',`${project}/${name}`,'--yes']);
    console.log(JSON.stringify({name,image,deployRequested:true,mode:'live',paused:true,youtubeEnabled:false}));
  } else if(action==='deploy-dashboard-fix-code') {
    const name=process.argv[3];
    if(!names.slice(1).includes(name)) throw new Error('Only NicheRadar apps can be updated');
    const isDashboard=name==='nicheradar-dashboard';
    const before=cli(['app','inspect',`${project}/${name}`]);
    const env=appEnv(name);
    const expected=isDashboard?youtubeDashboard:name==='nicheradar-worker'?youtubeWorker:youtubeBackend;
    if(before.source?.image!==expected || before.ports?.length ||
       before.deploy?.replicas!==1 || before.resources?.memoryLimit!==512 ||
       env.NR_MODE!=='live' || env.NR_RADAR_PAUSED!=='true' ||
       (!isDashboard && (!env.NR_VIDIQ_TOKEN || env.NR_VIDIQ_LIVE_ENABLED!=='true' || env.NR_VIDIQ_PILOT_AUTHORIZED!=='true')) ||
       (isDashboard && (env.NR_VIDIQ_TOKEN || env.NR_YOUTUBE_API_KEY)))
      throw new Error('Dashboard fix release preconditions failed');
    const image=isDashboard?dashboardFixDashboard:name==='nicheradar-worker'?dashboardFixWorker:dashboardFixBackend;
    cli(['app','update-source-image',`${project}/${name}`,'--yes'],{image});
    const after=cli(['app','inspect',`${project}/${name}`]);
    for(const field of ['env','resources','deploy','ports','mounts','basicAuth']) {
      if(JSON.stringify(before[field])!==JSON.stringify(after[field])) throw new Error('Unexpected configuration change; deployment not requested');
    }
    if(after.source?.image!==image) throw new Error('Image setting not persisted');
    cli(['app','deploy',`${project}/${name}`,'--yes']);
    console.log(JSON.stringify({name,image,deployRequested:true,mode:'live',paused:true}));
  } else if(action==='deploy-ui-redesign-code') {
    const name=process.argv[3];
    if(!names.slice(1).includes(name)) throw new Error('Only NicheRadar apps can be updated');
    const isDashboard=name==='nicheradar-dashboard';
    const before=cli(['app','inspect',`${project}/${name}`]);
    const env=appEnv(name);
    const expected=isDashboard?dashboardFixDashboard:name==='nicheradar-worker'?dashboardFixWorker:dashboardFixBackend;
    if(before.source?.image!==expected || before.ports?.length ||
       before.deploy?.replicas!==1 || before.resources?.memoryLimit!==512 ||
       env.NR_MODE!=='live' || env.NR_RADAR_PAUSED!=='true')
      throw new Error('UI redesign release preconditions failed');
    const image=isDashboard?uiRedesignDashboard:name==='nicheradar-worker'?uiRedesignWorker:uiRedesignBackend;
    cli(['app','update-source-image',`${project}/${name}`,'--yes'],{image});
    const after=cli(['app','inspect',`${project}/${name}`]);
    for(const field of ['env','resources','deploy','ports','mounts','basicAuth']) {
      if(JSON.stringify(before[field])!==JSON.stringify(after[field])) throw new Error('Unexpected configuration change; deployment not requested');
    }
    if(after.source?.image!==image) throw new Error('Image setting not persisted');
    cli(['app','deploy',`${project}/${name}`,'--yes']);
    console.log(JSON.stringify({name,image,deployRequested:true,mode:'live',paused:true}));
  } else if(action==='deploy-json-cleanup-code') {
    const name=process.argv[3];
    if(!names.slice(1).includes(name)) throw new Error('Only NicheRadar apps can be updated');
    const isDashboard=name==='nicheradar-dashboard';
    const before=cli(['app','inspect',`${project}/${name}`]);
    const env=appEnv(name);
    const expected=isDashboard?uiRedesignDashboard:name==='nicheradar-worker'?uiRedesignWorker:uiRedesignBackend;
    if(before.source?.image!==expected || before.ports?.length ||
       before.deploy?.replicas!==1 || before.resources?.memoryLimit!==512 ||
       env.NR_MODE!=='live' || env.NR_RADAR_PAUSED!=='true')
      throw new Error('JSON cleanup release preconditions failed');
    const image=isDashboard?jsonCleanupDashboard:name==='nicheradar-worker'?jsonCleanupWorker:jsonCleanupBackend;
    cli(['app','update-source-image',`${project}/${name}`,'--yes'],{image});
    const after=cli(['app','inspect',`${project}/${name}`]);
    for(const field of ['env','resources','deploy','ports','mounts','basicAuth']) {
      if(JSON.stringify(before[field])!==JSON.stringify(after[field])) throw new Error('Unexpected configuration change; deployment not requested');
    }
    if(after.source?.image!==image) throw new Error('Image setting not persisted');
    cli(['app','deploy',`${project}/${name}`,'--yes']);
    console.log(JSON.stringify({name,image,deployRequested:true,mode:'live',paused:true}));
  } else if(action==='migrate-live-0009') {
    const env=appEnv('nicheradar-api');
    if(env.NR_MODE!=='live' || env.NR_RADAR_PAUSED!=='true' || env.NR_DATABASE_URL!==dbURL())
      throw new Error('Live migration preconditions failed');
    const code='import json,os,subprocess,sys; os.environ.update(json.load(sys.stdin)); sys.exit(subprocess.call(["alembic","upgrade","head"]))';
    const args=['docker','run','--rm','-i','--name','nicheradar-migration-20260928-010',
      '--network','easypanel-proy1-credito-riesgo','--memory','512m','--cpus','1',
      '--read-only','--tmpfs','/tmp:rw,noexec,nosuid,size=64m','--cap-drop','ALL',
      '--security-opt','no-new-privileges',defaultRecipeBackend,'python','-c',code];
    const result=spawnSync('ssh',[...sshArgs,args.map(quote).join(' ')],{
      input:JSON.stringify({NR_DATABASE_URL:env.NR_DATABASE_URL}),
      encoding:'utf8',timeout:180000,maxBuffer:1024*1024});
    console.log(JSON.stringify({migrationExit:result.status,processError:result.error?.code ?? null}));
    if(result.error || result.status!==0) throw new Error('Migration failed; raw response withheld. Inspect only this migration safely.');
  } else if(action==='migrate-live-0010') {
    const env=appEnv('nicheradar-api');
    if(env.NR_MODE!=='live' || env.NR_RADAR_PAUSED!=='true' || env.NR_DATABASE_URL!==dbURL())
      throw new Error('Live migration preconditions failed');
    const code='import json,os,subprocess,sys; os.environ.update(json.load(sys.stdin)); sys.exit(subprocess.call(["alembic","upgrade","head"]))';
    const args=['docker','run','--rm','-i','--name','nicheradar-migration-20261002-011',
      '--network','easypanel-proy1-credito-riesgo','--memory','512m','--cpus','1',
      '--read-only','--tmpfs','/tmp:rw,noexec,nosuid,size=64m','--cap-drop','ALL',
      '--security-opt','no-new-privileges',channelAnalysisBackend,'python','-c',code];
    const result=spawnSync('ssh',[...sshArgs,args.map(quote).join(' ')],{
      input:JSON.stringify({NR_DATABASE_URL:env.NR_DATABASE_URL}),
      encoding:'utf8',timeout:180000,maxBuffer:1024*1024});
    console.log(JSON.stringify({migrationExit:result.status,processError:result.error?.code ?? null}));
    if(result.error || result.status!==0) throw new Error('Migration failed; raw response withheld. Inspect only this migration safely.');
  } else if(action==='migrate-live-0012') {
    const env=appEnv('nicheradar-api');
    if(env.NR_MODE!=='live' || env.NR_RADAR_PAUSED!=='true' || env.NR_DATABASE_URL!==dbURL())
      throw new Error('Live migration preconditions failed');
    const code='import json,os,subprocess,sys; os.environ.update(json.load(sys.stdin)); sys.exit(subprocess.call(["alembic","upgrade","head"]))';
    const args=['docker','run','--rm','-i','--name','nicheradar-migration-20261003-012',
      '--network','easypanel-proy1-credito-riesgo','--memory','512m','--cpus','1',
      '--read-only','--tmpfs','/tmp:rw,noexec,nosuid,size=64m','--cap-drop','ALL',
      '--security-opt','no-new-privileges',insightsScoreBackend,'python','-c',code];
    const result=spawnSync('ssh',[...sshArgs,args.map(quote).join(' ')],{
      input:JSON.stringify({NR_DATABASE_URL:env.NR_DATABASE_URL}),
      encoding:'utf8',timeout:180000,maxBuffer:1024*1024});
    console.log(JSON.stringify({migrationExit:result.status,processError:result.error?.code ?? null}));
    if(result.error || result.status!==0) throw new Error('Migration failed; raw response withheld. Inspect only this migration safely.');
  } else if(action==='deploy-batch-size-crash-fix-code') {
    const name=process.argv[3];
    if(!names.slice(1).includes(name)) throw new Error('Only NicheRadar apps can be updated');
    const isDashboard=name==='nicheradar-dashboard';
    const before=cli(['app','inspect',`${project}/${name}`]);
    const env=appEnv(name);
    const expected=isDashboard?insightsScoreDashboard:name==='nicheradar-worker'?insightsScoreWorker:insightsScoreBackend;
    if(before.source?.image!==expected || before.ports?.length ||
       before.deploy?.replicas!==1 || before.resources?.memoryLimit!==512 ||
       env.NR_MODE!=='live' || env.NR_RADAR_PAUSED!=='true')
      throw new Error('Batch size crash fix release preconditions failed');
    const image=isDashboard?batchSizeCrashFixDashboard:name==='nicheradar-worker'?batchSizeCrashFixWorker:batchSizeCrashFixBackend;
    cli(['app','update-source-image',`${project}/${name}`,'--yes'],{image});
    const after=cli(['app','inspect',`${project}/${name}`]);
    for(const field of ['env','resources','deploy','ports','mounts','basicAuth']) {
      if(JSON.stringify(before[field])!==JSON.stringify(after[field])) throw new Error('Unexpected configuration change; deployment not requested');
    }
    if(after.source?.image!==image) throw new Error('Image setting not persisted');
    cli(['app','deploy',`${project}/${name}`,'--yes']);
    console.log(JSON.stringify({name,image,deployRequested:true,mode:'live',paused:true}));
  } else if(action==='migrate-live-0014') {
    const env=appEnv('nicheradar-api');
    if(env.NR_MODE!=='live' || env.NR_RADAR_PAUSED!=='true' || env.NR_DATABASE_URL!==dbURL() ||
       env.NR_MARKET_INTEL_LIVE_ENABLED==='true')
      throw new Error('Live migration preconditions failed');
    const code='import json,os,subprocess,sys; os.environ.update(json.load(sys.stdin)); sys.exit(subprocess.call(["alembic","upgrade","head"]))';
    const args=['docker','run','--rm','-i','--name','nicheradar-migration-20261025-012',
      '--network','easypanel-proy1-credito-riesgo','--memory','512m','--cpus','1',
      '--read-only','--tmpfs','/tmp:rw,noexec,nosuid,size=64m','--cap-drop','ALL',
      '--security-opt','no-new-privileges',marketFlowBackend,'python','-c',code];
    const result=spawnSync('ssh',[...sshArgs,args.map(quote).join(' ')],{
      input:JSON.stringify({NR_DATABASE_URL:env.NR_DATABASE_URL}),
      encoding:'utf8',timeout:180000,maxBuffer:1024*1024});
    console.log(JSON.stringify({migrationExit:result.status,processError:result.error?.code ?? null}));
    if(result.error || result.status!==0) throw new Error('Migration failed; raw response withheld. Inspect only this migration safely.');
  } else if(action==='deploy-market-flow-code') {
    const name=process.argv[3];
    if(!names.slice(1).includes(name)) throw new Error('Only NicheRadar apps can be updated');
    const isDashboard=name==='nicheradar-dashboard';
    const before=cli(['app','inspect',`${project}/${name}`]);
    const env=appEnv(name);
    const expected=isDashboard?batchSizeCrashFixDashboard:name==='nicheradar-worker'?batchSizeCrashFixWorker:batchSizeCrashFixBackend;
    if(before.source?.image!==expected || before.ports?.length ||
       before.deploy?.replicas!==1 || before.resources?.memoryLimit!==512 ||
       env.NR_MODE!=='live' || env.NR_RADAR_PAUSED!=='true' ||
       env.NR_MARKET_INTEL_LIVE_ENABLED==='true')
      throw new Error('Market intel and flow research release preconditions failed');
    const image=isDashboard?marketFlowDashboard:name==='nicheradar-worker'?marketFlowWorker:marketFlowBackend;
    cli(['app','update-source-image',`${project}/${name}`,'--yes'],{image});
    const after=cli(['app','inspect',`${project}/${name}`]);
    for(const field of ['env','resources','deploy','ports','mounts','basicAuth']) {
      if(JSON.stringify(before[field])!==JSON.stringify(after[field])) throw new Error('Unexpected configuration change; deployment not requested');
    }
    if(after.source?.image!==image) throw new Error('Image setting not persisted');
    cli(['app','deploy',`${project}/${name}`,'--yes']);
    console.log(JSON.stringify({name,image,deployRequested:true,mode:'live',paused:true}));
  } else if(action==='migrate-live-0015') {
    const env=appEnv('nicheradar-api');
    // NR_MARKET_INTEL_LIVE_ENABLED puede ser true (decisión del propietario tras 012): se exige
    // que el radar esté pausado y se comprueba aparte que la programación de mercado también.
    if(env.NR_MODE!=='live' || env.NR_RADAR_PAUSED!=='true' || env.NR_DATABASE_URL!==dbURL())
      throw new Error('Live migration preconditions failed');
    const code='import json,os,subprocess,sys; os.environ.update(json.load(sys.stdin)); sys.exit(subprocess.call(["alembic","upgrade","head"]))';
    const args=['docker','run','--rm','-i','--name','nicheradar-migration-20261025-013',
      '--network','easypanel-proy1-credito-riesgo','--memory','512m','--cpus','1',
      '--read-only','--tmpfs','/tmp:rw,noexec,nosuid,size=64m','--cap-drop','ALL',
      '--security-opt','no-new-privileges',pilotsBackend,'python','-c',code];
    const result=spawnSync('ssh',[...sshArgs,args.map(quote).join(' ')],{
      input:JSON.stringify({NR_DATABASE_URL:env.NR_DATABASE_URL}),
      encoding:'utf8',timeout:180000,maxBuffer:1024*1024});
    console.log(JSON.stringify({migrationExit:result.status,processError:result.error?.code ?? null}));
    if(result.error || result.status!==0) throw new Error('Migration failed; raw response withheld. Inspect only this migration safely.');
  } else if(action==='deploy-pilots-code') {
    const name=process.argv[3];
    if(!names.slice(1).includes(name)) throw new Error('Only NicheRadar apps can be updated');
    const isDashboard=name==='nicheradar-dashboard';
    const before=cli(['app','inspect',`${project}/${name}`]);
    const env=appEnv(name);
    const expected=isDashboard?marketFlowDashboard:name==='nicheradar-worker'?marketFlowWorker:marketFlowBackend;
    if(before.source?.image!==expected || before.ports?.length ||
       before.deploy?.replicas!==1 || before.resources?.memoryLimit!==512 ||
       env.NR_MODE!=='live' || env.NR_RADAR_PAUSED!=='true')
      throw new Error('Pilots release preconditions failed');
    const image=isDashboard?pilotsDashboard:name==='nicheradar-worker'?pilotsWorker:pilotsBackend;
    cli(['app','update-source-image',`${project}/${name}`,'--yes'],{image});
    const after=cli(['app','inspect',`${project}/${name}`]);
    for(const field of ['env','resources','deploy','ports','mounts','basicAuth']) {
      if(JSON.stringify(before[field])!==JSON.stringify(after[field])) throw new Error('Unexpected configuration change; deployment not requested');
    }
    if(after.source?.image!==image) throw new Error('Image setting not persisted');
    cli(['app','deploy',`${project}/${name}`,'--yes']);
    console.log(JSON.stringify({name,image,deployRequested:true,mode:'live',paused:true}));
  } else if(action==='migrate-live-0016') {
    const env=appEnv('nicheradar-api');
    // NR_MARKET_INTEL_LIVE_ENABLED puede ser true (decisión del propietario tras 012): se exige
    // que el radar esté pausado y se comprueba aparte que la programación de mercado también.
    if(env.NR_MODE!=='live' || env.NR_RADAR_PAUSED!=='true' || env.NR_DATABASE_URL!==dbURL())
      throw new Error('Live migration preconditions failed');
    const code='import json,os,subprocess,sys; os.environ.update(json.load(sys.stdin)); sys.exit(subprocess.call(["alembic","upgrade","head"]))';
    const args=['docker','run','--rm','-i','--name','nicheradar-migration-20261025-014',
      '--network','easypanel-proy1-credito-riesgo','--memory','512m','--cpus','1',
      '--read-only','--tmpfs','/tmp:rw,noexec,nosuid,size=64m','--cap-drop','ALL',
      '--security-opt','no-new-privileges',languageBackend,'python','-c',code];
    const result=spawnSync('ssh',[...sshArgs,args.map(quote).join(' ')],{
      input:JSON.stringify({NR_DATABASE_URL:env.NR_DATABASE_URL}),
      encoding:'utf8',timeout:180000,maxBuffer:1024*1024});
    console.log(JSON.stringify({migrationExit:result.status,processError:result.error?.code ?? null}));
    if(result.error || result.status!==0) throw new Error('Migration failed; raw response withheld. Inspect only this migration safely.');
  } else if(action==='deploy-language-code') {
    const name=process.argv[3];
    if(!names.slice(1).includes(name)) throw new Error('Only NicheRadar apps can be updated');
    const isDashboard=name==='nicheradar-dashboard';
    const before=cli(['app','inspect',`${project}/${name}`]);
    const env=appEnv(name);
    const expected=isDashboard?pilotsDashboard:name==='nicheradar-worker'?pilotsWorker:pilotsBackend;
    if(before.source?.image!==expected || before.ports?.length ||
       before.deploy?.replicas!==1 || before.resources?.memoryLimit!==512 ||
       env.NR_MODE!=='live' || env.NR_RADAR_PAUSED!=='true')
      throw new Error('Language release preconditions failed');
    const image=isDashboard?languageDashboard:name==='nicheradar-worker'?languageWorker:languageBackend;
    cli(['app','update-source-image',`${project}/${name}`,'--yes'],{image});
    const after=cli(['app','inspect',`${project}/${name}`]);
    for(const field of ['env','resources','deploy','ports','mounts','basicAuth']) {
      if(JSON.stringify(before[field])!==JSON.stringify(after[field])) throw new Error('Unexpected configuration change; deployment not requested');
    }
    if(after.source?.image!==image) throw new Error('Image setting not persisted');
    cli(['app','deploy',`${project}/${name}`,'--yes']);
    console.log(JSON.stringify({name,image,deployRequested:true,mode:'live',paused:true}));
  } else if(action==='deploy-stop-rules-code') {
    const name=process.argv[3];
    if(!names.slice(1).includes(name)) throw new Error('Only NicheRadar apps can be updated');
    const isDashboard=name==='nicheradar-dashboard';
    const before=cli(['app','inspect',`${project}/${name}`]);
    const env=appEnv(name);
    const expected=isDashboard?languageDashboard:name==='nicheradar-worker'?languageWorker:languageBackend;
    if(before.source?.image!==expected || before.ports?.length ||
       before.deploy?.replicas!==1 || before.resources?.memoryLimit!==512 ||
       env.NR_MODE!=='live' || env.NR_RADAR_PAUSED!=='true')
      throw new Error('Stop rules release preconditions failed');
    const image=isDashboard?stopRulesDashboard:name==='nicheradar-worker'?stopRulesWorker:stopRulesBackend;
    cli(['app','update-source-image',`${project}/${name}`,'--yes'],{image});
    const after=cli(['app','inspect',`${project}/${name}`]);
    for(const field of ['env','resources','deploy','ports','mounts','basicAuth']) {
      if(JSON.stringify(before[field])!==JSON.stringify(after[field])) throw new Error('Unexpected configuration change; deployment not requested');
    }
    if(after.source?.image!==image) throw new Error('Image setting not persisted');
    cli(['app','deploy',`${project}/${name}`,'--yes']);
    console.log(JSON.stringify({name,image,deployRequested:true,mode:'live',paused:true}));
  } else if(action==='migrate-live-0020') {
    const env=appEnv('nicheradar-api');
    // Revisión 0020: tablas del descubrimiento de subnichos (aditiva). Exige radar pausado, como las anteriores.
    if(env.NR_MODE!=='live' || env.NR_RADAR_PAUSED!=='true' || env.NR_DATABASE_URL!==dbURL())
      throw new Error('Live migration preconditions failed');
    const code='import json,os,subprocess,sys; os.environ.update(json.load(sys.stdin)); sys.exit(subprocess.call(["alembic","upgrade","head"]))';
    const args=['docker','run','--rm','-i','--name','nicheradar-migration-20261031-020',
      '--network','easypanel-proy1-credito-riesgo','--memory','512m','--cpus','1',
      '--read-only','--tmpfs','/tmp:rw,noexec,nosuid,size=64m','--cap-drop','ALL',
      '--security-opt','no-new-privileges',subnicheBackend,'python','-c',code];
    const result=spawnSync('ssh',[...sshArgs,args.map(quote).join(' ')],{
      input:JSON.stringify({NR_DATABASE_URL:env.NR_DATABASE_URL}),
      encoding:'utf8',timeout:180000,maxBuffer:1024*1024});
    console.log(JSON.stringify({migrationExit:result.status,processError:result.error?.code ?? null}));
    if(result.error || result.status!==0) throw new Error('Migration failed; raw response withheld. Inspect only this migration safely.');
  } else if(action==='deploy-subniche-code') {
    const name=process.argv[3];
    if(!names.slice(1).includes(name)) throw new Error('Only NicheRadar apps can be updated');
    const isDashboard=name==='nicheradar-dashboard';
    const before=cli(['app','inspect',`${project}/${name}`]);
    const env=appEnv(name);
    const expected=isDashboard?isolatedIncomeDashboard:name==='nicheradar-worker'?isolatedIncomeWorker:isolatedIncomeBackend;
    if(before.source?.image!==expected || before.ports?.length ||
       before.deploy?.replicas!==1 || before.resources?.memoryLimit!==512 ||
       env.NR_MODE!=='live' || env.NR_RADAR_PAUSED!=='true')
      throw new Error('Subniche release preconditions failed');
    const image=isDashboard?subnicheDashboard:name==='nicheradar-worker'?subnicheWorker:subnicheBackend;
    cli(['app','update-source-image',`${project}/${name}`,'--yes'],{image});
    const after=cli(['app','inspect',`${project}/${name}`]);
    for(const field of ['env','resources','deploy','ports','mounts','basicAuth']) {
      if(JSON.stringify(before[field])!==JSON.stringify(after[field])) throw new Error('Unexpected configuration change; deployment not requested');
    }
    if(after.source?.image!==image) throw new Error('Image setting not persisted');
    cli(['app','deploy',`${project}/${name}`,'--yes']);
    console.log(JSON.stringify({name,image,deployRequested:true,mode:'live',paused:true}));
  } else if(action==='set-subniche-env') {
    // Variables del descubrimiento de subnichos en el worker (docs/subniche-discovery.md). Uso: set-subniche-env [dry].
    // NR_SUBNICHE_ENABLED NO se toca: sigue desactivado hasta que el propietario revise la lista de hipótesis.
    // Nunca imprime el entorno ni la clave; solo los nombres y valores no secretos que cambia.
    const name='nicheradar-worker';
    const before=cli(['app','inspect',`${project}/${name}`]);
    const env=appEnv(name);
    if(env.NR_MODE!=='live' || env.NR_RADAR_PAUSED!=='true') throw new Error('Subniche env preconditions failed');
    // La clave se toma del entorno del worker si ya está guardada; si no, del .env local privado (nunca se imprime).
    const anthropicKey=env.NR_ANTHROPIC_API_KEY || localAnthropicKey();
    if(/\s/.test(anthropicKey)) throw new Error('Invalid Anthropic key');
    if(env.NR_SUBNICHE_ENABLED==='true') throw new Error('NR_SUBNICHE_ENABLED is already true; refusing to touch it');
    const configuration={auth_scope:'anthropic-owner',
      tariff:{version:'anthropic-sonnet-5-5-2026-10-31',model:'claude-sonnet-5-5',
        source:'https://platform.claude.com/docs/en/about-claude/pricing',
        verified_at:'2026-10-31T00:00:00Z',valid_until:'2027-01-29T00:00:00Z',
        context_window_tokens:16000,output_tokens:800,input_usd_per_million:'2',
        cached_input_usd_per_million:'0.10',output_usd_per_million:'10'},
      limits:{operation:'100',run:'1000',week:'10000',period:'100000'},timeout_seconds:20};
    const settings={NR_ANTHROPIC_ENABLED:'true',
      NR_SUBNICHE_SEARCH_UNITS_PER_DAY:'5000',NR_SUBNICHE_SEARCH_QUOTA_PER_RUN:'5000',
      NR_SUBNICHE_SEARCH_QUOTA_PER_WEEK:'35000',NR_SUBNICHE_SEARCH_QUOTA_PER_MONTH:'150000'};
    const dryRun=process.argv[3]==='dry';
    const result={name,set:Object.keys(settings).concat(['NR_ANTHROPIC_CONFIGURATION']),subnicheEnabled:env.NR_SUBNICHE_ENABLED ?? 'unset',dryRun};
    if(dryRun) {
      console.log(JSON.stringify(result));
    } else {
      const next={...env,...settings,NR_ANTHROPIC_API_KEY:anthropicKey,NR_ANTHROPIC_CONFIGURATION:JSON.stringify(configuration)};
      cli(['app','update-env',`${project}/${name}`,'--yes'],{env:Object.entries(next).map(([k,v])=>`${k}=${v}`).join('\n')});
      const after=cli(['app','inspect',`${project}/${name}`]);
      for(const field of ['source','resources','deploy','ports','mounts','basicAuth']) {
        if(JSON.stringify(before[field])!==JSON.stringify(after[field])) throw new Error('Unexpected non-environment change');
      }
      cli(['app','deploy',`${project}/${name}`,'--yes']);
      console.log(JSON.stringify({...result,deployRequested:true}));
    }
  } else if(action==='migrate-live-0019') {
    const env=appEnv('nicheradar-api');
    // NR_MARKET_INTEL_LIVE_ENABLED puede ser true (decisión del propietario tras 012): se exige
    // que el radar esté pausado y se comprueba aparte que la programación de mercado también.
    if(env.NR_MODE!=='live' || env.NR_RADAR_PAUSED!=='true' || env.NR_DATABASE_URL!==dbURL())
      throw new Error('Live migration preconditions failed');
    const code='import json,os,subprocess,sys; os.environ.update(json.load(sys.stdin)); sys.exit(subprocess.call(["alembic","upgrade","head"]))';
    const args=['docker','run','--rm','-i','--name','nicheradar-migration-20261028-019',
      '--network','easypanel-proy1-credito-riesgo','--memory','512m','--cpus','1',
      '--read-only','--tmpfs','/tmp:rw,noexec,nosuid,size=64m','--cap-drop','ALL',
      '--security-opt','no-new-privileges',evidenceBackend,'python','-c',code];
    const result=spawnSync('ssh',[...sshArgs,args.map(quote).join(' ')],{
      input:JSON.stringify({NR_DATABASE_URL:env.NR_DATABASE_URL}),
      encoding:'utf8',timeout:180000,maxBuffer:1024*1024});
    console.log(JSON.stringify({migrationExit:result.status,processError:result.error?.code ?? null}));
    if(result.error || result.status!==0) throw new Error('Migration failed; raw response withheld. Inspect only this migration safely.');
  } else if(action==='migrate-live-0018') {
    const env=appEnv('nicheradar-api');
    // NR_MARKET_INTEL_LIVE_ENABLED puede ser true (decisión del propietario tras 012): se exige
    // que el radar esté pausado y se comprueba aparte que la programación de mercado también.
    if(env.NR_MODE!=='live' || env.NR_RADAR_PAUSED!=='true' || env.NR_DATABASE_URL!==dbURL())
      throw new Error('Live migration preconditions failed');
    const code='import json,os,subprocess,sys; os.environ.update(json.load(sys.stdin)); sys.exit(subprocess.call(["alembic","upgrade","head"]))';
    const args=['docker','run','--rm','-i','--name','nicheradar-migration-20261028-018',
      '--network','easypanel-proy1-credito-riesgo','--memory','512m','--cpus','1',
      '--read-only','--tmpfs','/tmp:rw,noexec,nosuid,size=64m','--cap-drop','ALL',
      '--security-opt','no-new-privileges',enrichBackend,'python','-c',code];
    const result=spawnSync('ssh',[...sshArgs,args.map(quote).join(' ')],{
      input:JSON.stringify({NR_DATABASE_URL:env.NR_DATABASE_URL}),
      encoding:'utf8',timeout:180000,maxBuffer:1024*1024});
    console.log(JSON.stringify({migrationExit:result.status,processError:result.error?.code ?? null}));
    if(result.error || result.status!==0) throw new Error('Migration failed; raw response withheld. Inspect only this migration safely.');
  } else if(action==='migrate-live-0017') {
    const env=appEnv('nicheradar-api');
    // NR_MARKET_INTEL_LIVE_ENABLED puede ser true (decisión del propietario tras 012): se exige
    // que el radar esté pausado y se comprueba aparte que la programación de mercado también.
    if(env.NR_MODE!=='live' || env.NR_RADAR_PAUSED!=='true' || env.NR_DATABASE_URL!==dbURL())
      throw new Error('Live migration preconditions failed');
    const code='import json,os,subprocess,sys; os.environ.update(json.load(sys.stdin)); sys.exit(subprocess.call(["alembic","upgrade","head"]))';
    const args=['docker','run','--rm','-i','--name','nicheradar-migration-20261026-016',
      '--network','easypanel-proy1-credito-riesgo','--memory','512m','--cpus','1',
      '--read-only','--tmpfs','/tmp:rw,noexec,nosuid,size=64m','--cap-drop','ALL',
      '--security-opt','no-new-privileges',shortsReportBackend,'python','-c',code];
    const result=spawnSync('ssh',[...sshArgs,args.map(quote).join(' ')],{
      input:JSON.stringify({NR_DATABASE_URL:env.NR_DATABASE_URL}),
      encoding:'utf8',timeout:180000,maxBuffer:1024*1024});
    console.log(JSON.stringify({migrationExit:result.status,processError:result.error?.code ?? null}));
    if(result.error || result.status!==0) throw new Error('Migration failed; raw response withheld. Inspect only this migration safely.');
  } else if(action==='deploy-shorts-report-code') {
    const name=process.argv[3];
    if(!names.slice(1).includes(name)) throw new Error('Only NicheRadar apps can be updated');
    const isDashboard=name==='nicheradar-dashboard';
    const before=cli(['app','inspect',`${project}/${name}`]);
    const env=appEnv(name);
    const expected=isDashboard?stopRulesDashboard:name==='nicheradar-worker'?stopRulesWorker:stopRulesBackend;
    if(before.source?.image!==expected || before.ports?.length ||
       before.deploy?.replicas!==1 || before.resources?.memoryLimit!==512 ||
       env.NR_MODE!=='live' || env.NR_RADAR_PAUSED!=='true')
      throw new Error('Shorts report release preconditions failed');
    const image=isDashboard?shortsReportDashboard:name==='nicheradar-worker'?shortsReportWorker:shortsReportBackend;
    cli(['app','update-source-image',`${project}/${name}`,'--yes'],{image});
    const after=cli(['app','inspect',`${project}/${name}`]);
    for(const field of ['env','resources','deploy','ports','mounts','basicAuth']) {
      if(JSON.stringify(before[field])!==JSON.stringify(after[field])) throw new Error('Unexpected configuration change; deployment not requested');
    }
    if(after.source?.image!==image) throw new Error('Image setting not persisted');
    cli(['app','deploy',`${project}/${name}`,'--yes']);
    console.log(JSON.stringify({name,image,deployRequested:true,mode:'live',paused:true}));
  } else if(action==='deploy-gates-code') {
    const name=process.argv[3];
    if(!names.slice(1).includes(name)) throw new Error('Only NicheRadar apps can be updated');
    const isDashboard=name==='nicheradar-dashboard';
    const before=cli(['app','inspect',`${project}/${name}`]);
    const env=appEnv(name);
    const expected=isDashboard?shortsReportDashboard:name==='nicheradar-worker'?shortsReportWorker:shortsReportBackend;
    if(before.source?.image!==expected || before.ports?.length ||
       before.deploy?.replicas!==1 || before.resources?.memoryLimit!==512 ||
       env.NR_MODE!=='live' || env.NR_RADAR_PAUSED!=='true')
      throw new Error('Gates release preconditions failed');
    const image=isDashboard?gatesDashboard:name==='nicheradar-worker'?gatesWorker:gatesBackend;
    cli(['app','update-source-image',`${project}/${name}`,'--yes'],{image});
    const after=cli(['app','inspect',`${project}/${name}`]);
    for(const field of ['env','resources','deploy','ports','mounts','basicAuth']) {
      if(JSON.stringify(before[field])!==JSON.stringify(after[field])) throw new Error('Unexpected configuration change; deployment not requested');
    }
    if(after.source?.image!==image) throw new Error('Image setting not persisted');
    cli(['app','deploy',`${project}/${name}`,'--yes']);
    console.log(JSON.stringify({name,image,deployRequested:true,mode:'live',paused:true}));
  } else if(action==='deploy-batch-limit-code') {
    const name=process.argv[3];
    if(!names.slice(1).includes(name)) throw new Error('Only NicheRadar apps can be updated');
    const isDashboard=name==='nicheradar-dashboard';
    const before=cli(['app','inspect',`${project}/${name}`]);
    const env=appEnv(name);
    const expected=isDashboard?gatesDashboard:name==='nicheradar-worker'?gatesWorker:gatesBackend;
    if(before.source?.image!==expected || before.ports?.length ||
       before.deploy?.replicas!==1 || before.resources?.memoryLimit!==512 ||
       env.NR_MODE!=='live' || env.NR_RADAR_PAUSED!=='true')
      throw new Error('Batch limit release preconditions failed');
    const image=isDashboard?batchDashboard:name==='nicheradar-worker'?batchWorker:batchBackend;
    cli(['app','update-source-image',`${project}/${name}`,'--yes'],{image});
    const after=cli(['app','inspect',`${project}/${name}`]);
    for(const field of ['env','resources','deploy','ports','mounts','basicAuth']) {
      if(JSON.stringify(before[field])!==JSON.stringify(after[field])) throw new Error('Unexpected configuration change; deployment not requested');
    }
    if(after.source?.image!==image) throw new Error('Image setting not persisted');
    cli(['app','deploy',`${project}/${name}`,'--yes']);
    console.log(JSON.stringify({name,image,deployRequested:true,mode:'live',paused:true}));
  } else if(action==='deploy-classify-skip-code') {
    const name=process.argv[3];
    if(!names.slice(1).includes(name)) throw new Error('Only NicheRadar apps can be updated');
    const isDashboard=name==='nicheradar-dashboard';
    const before=cli(['app','inspect',`${project}/${name}`]);
    const env=appEnv(name);
    const expected=isDashboard?batchDashboard:name==='nicheradar-worker'?batchWorker:batchBackend;
    if(before.source?.image!==expected || before.ports?.length ||
       before.deploy?.replicas!==1 || before.resources?.memoryLimit!==512 ||
       env.NR_MODE!=='live' || env.NR_RADAR_PAUSED!=='true')
      throw new Error('Classify skip release preconditions failed');
    const image=isDashboard?classifyDashboard:name==='nicheradar-worker'?classifyWorker:classifyBackend;
    cli(['app','update-source-image',`${project}/${name}`,'--yes'],{image});
    const after=cli(['app','inspect',`${project}/${name}`]);
    for(const field of ['env','resources','deploy','ports','mounts','basicAuth']) {
      if(JSON.stringify(before[field])!==JSON.stringify(after[field])) throw new Error('Unexpected configuration change; deployment not requested');
    }
    if(after.source?.image!==image) throw new Error('Image setting not persisted');
    cli(['app','deploy',`${project}/${name}`,'--yes']);
    console.log(JSON.stringify({name,image,deployRequested:true,mode:'live',paused:true}));
  } else if(action==='deploy-enrich-code') {
    const name=process.argv[3];
    if(!names.slice(1).includes(name)) throw new Error('Only NicheRadar apps can be updated');
    const isDashboard=name==='nicheradar-dashboard';
    const before=cli(['app','inspect',`${project}/${name}`]);
    const env=appEnv(name);
    const expected=isDashboard?classifyDashboard:name==='nicheradar-worker'?classifyWorker:classifyBackend;
    if(before.source?.image!==expected || before.ports?.length ||
       before.deploy?.replicas!==1 || before.resources?.memoryLimit!==512 ||
       env.NR_MODE!=='live' || env.NR_RADAR_PAUSED!=='true')
      throw new Error('Enrich release preconditions failed');
    const image=isDashboard?enrichDashboard:name==='nicheradar-worker'?enrichWorker:enrichBackend;
    cli(['app','update-source-image',`${project}/${name}`,'--yes'],{image});
    const after=cli(['app','inspect',`${project}/${name}`]);
    for(const field of ['env','resources','deploy','ports','mounts','basicAuth']) {
      if(JSON.stringify(before[field])!==JSON.stringify(after[field])) throw new Error('Unexpected configuration change; deployment not requested');
    }
    if(after.source?.image!==image) throw new Error('Image setting not persisted');
    cli(['app','deploy',`${project}/${name}`,'--yes']);
    console.log(JSON.stringify({name,image,deployRequested:true,mode:'live',paused:true}));
  } else if(action==='deploy-enrich-fix-code') {
    const name=process.argv[3];
    if(!names.slice(1).includes(name)) throw new Error('Only NicheRadar apps can be updated');
    const isDashboard=name==='nicheradar-dashboard';
    const before=cli(['app','inspect',`${project}/${name}`]);
    const env=appEnv(name);
    const expected=isDashboard?enrichDashboard:name==='nicheradar-worker'?enrichWorker:enrichBackend;
    if(before.source?.image!==expected || before.ports?.length ||
       before.deploy?.replicas!==1 || before.resources?.memoryLimit!==512 ||
       env.NR_MODE!=='live' || env.NR_RADAR_PAUSED!=='true')
      throw new Error('Enrich fix release preconditions failed');
    const image=isDashboard?enrichFixDashboard:name==='nicheradar-worker'?enrichFixWorker:enrichFixBackend;
    cli(['app','update-source-image',`${project}/${name}`,'--yes'],{image});
    const after=cli(['app','inspect',`${project}/${name}`]);
    for(const field of ['env','resources','deploy','ports','mounts','basicAuth']) {
      if(JSON.stringify(before[field])!==JSON.stringify(after[field])) throw new Error('Unexpected configuration change; deployment not requested');
    }
    if(after.source?.image!==image) throw new Error('Image setting not persisted');
    cli(['app','deploy',`${project}/${name}`,'--yes']);
    console.log(JSON.stringify({name,image,deployRequested:true,mode:'live',paused:true}));
  } else if(action==='deploy-evidence-code') {
    const name=process.argv[3];
    if(!names.slice(1).includes(name)) throw new Error('Only NicheRadar apps can be updated');
    const isDashboard=name==='nicheradar-dashboard';
    const before=cli(['app','inspect',`${project}/${name}`]);
    const env=appEnv(name);
    const expected=isDashboard?enrichFixDashboard:name==='nicheradar-worker'?enrichFixWorker:enrichFixBackend;
    if(before.source?.image!==expected || before.ports?.length ||
       before.deploy?.replicas!==1 || before.resources?.memoryLimit!==512 ||
       env.NR_MODE!=='live' || env.NR_RADAR_PAUSED!=='true')
      throw new Error('Evidence release preconditions failed');
    const image=isDashboard?evidenceDashboard:name==='nicheradar-worker'?evidenceWorker:evidenceBackend;
    cli(['app','update-source-image',`${project}/${name}`,'--yes'],{image});
    const after=cli(['app','inspect',`${project}/${name}`]);
    for(const field of ['env','resources','deploy','ports','mounts','basicAuth']) {
      if(JSON.stringify(before[field])!==JSON.stringify(after[field])) throw new Error('Unexpected configuration change; deployment not requested');
    }
    if(after.source?.image!==image) throw new Error('Image setting not persisted');
    cli(['app','deploy',`${project}/${name}`,'--yes']);
    console.log(JSON.stringify({name,image,deployRequested:true,mode:'live',paused:true}));
  } else if(action==='deploy-evidence-fix-code') {
    const name=process.argv[3];
    if(!names.slice(1).includes(name)) throw new Error('Only NicheRadar apps can be updated');
    const isDashboard=name==='nicheradar-dashboard';
    const before=cli(['app','inspect',`${project}/${name}`]);
    const env=appEnv(name);
    const expected=isDashboard?evidenceDashboard:name==='nicheradar-worker'?evidenceWorker:evidenceBackend;
    if(before.source?.image!==expected || before.ports?.length ||
       before.deploy?.replicas!==1 || before.resources?.memoryLimit!==512 ||
       env.NR_MODE!=='live' || env.NR_RADAR_PAUSED!=='true')
      throw new Error('Evidence fix release preconditions failed');
    const image=isDashboard?evidenceFixDashboard:name==='nicheradar-worker'?evidenceFixWorker:evidenceFixBackend;
    cli(['app','update-source-image',`${project}/${name}`,'--yes'],{image});
    const after=cli(['app','inspect',`${project}/${name}`]);
    for(const field of ['env','resources','deploy','ports','mounts','basicAuth']) {
      if(JSON.stringify(before[field])!==JSON.stringify(after[field])) throw new Error('Unexpected configuration change; deployment not requested');
    }
    if(after.source?.image!==image) throw new Error('Image setting not persisted');
    cli(['app','deploy',`${project}/${name}`,'--yes']);
    console.log(JSON.stringify({name,image,deployRequested:true,mode:'live',paused:true}));
  } else if(action==='deploy-evidence-tolerant-code') {
    const name=process.argv[3];
    if(!names.slice(1).includes(name)) throw new Error('Only NicheRadar apps can be updated');
    const isDashboard=name==='nicheradar-dashboard';
    const before=cli(['app','inspect',`${project}/${name}`]);
    const env=appEnv(name);
    const expected=isDashboard?evidenceFixDashboard:name==='nicheradar-worker'?evidenceFixWorker:evidenceFixBackend;
    if(before.source?.image!==expected || before.ports?.length ||
       before.deploy?.replicas!==1 || before.resources?.memoryLimit!==512 ||
       env.NR_MODE!=='live' || env.NR_RADAR_PAUSED!=='true')
      throw new Error('Evidence tolerant release preconditions failed');
    const image=isDashboard?evidenceTolDashboard:name==='nicheradar-worker'?evidenceTolWorker:evidenceTolBackend;
    cli(['app','update-source-image',`${project}/${name}`,'--yes'],{image});
    const after=cli(['app','inspect',`${project}/${name}`]);
    for(const field of ['env','resources','deploy','ports','mounts','basicAuth']) {
      if(JSON.stringify(before[field])!==JSON.stringify(after[field])) throw new Error('Unexpected configuration change; deployment not requested');
    }
    if(after.source?.image!==image) throw new Error('Image setting not persisted');
    cli(['app','deploy',`${project}/${name}`,'--yes']);
    console.log(JSON.stringify({name,image,deployRequested:true,mode:'live',paused:true}));
  } else if(action==='deploy-evidence-relative-code') {
    const name=process.argv[3];
    if(!names.slice(1).includes(name)) throw new Error('Only NicheRadar apps can be updated');
    const isDashboard=name==='nicheradar-dashboard';
    const before=cli(['app','inspect',`${project}/${name}`]);
    const env=appEnv(name);
    const expected=isDashboard?evidenceTolDashboard:name==='nicheradar-worker'?evidenceTolWorker:evidenceTolBackend;
    if(before.source?.image!==expected || before.ports?.length ||
       before.deploy?.replicas!==1 || before.resources?.memoryLimit!==512 ||
       env.NR_MODE!=='live' || env.NR_RADAR_PAUSED!=='true')
      throw new Error('Evidence relative release preconditions failed');
    const image=isDashboard?evidenceRelDashboard:name==='nicheradar-worker'?evidenceRelWorker:evidenceRelBackend;
    cli(['app','update-source-image',`${project}/${name}`,'--yes'],{image});
    const after=cli(['app','inspect',`${project}/${name}`]);
    for(const field of ['env','resources','deploy','ports','mounts','basicAuth']) {
      if(JSON.stringify(before[field])!==JSON.stringify(after[field])) throw new Error('Unexpected configuration change; deployment not requested');
    }
    if(after.source?.image!==image) throw new Error('Image setting not persisted');
    cli(['app','deploy',`${project}/${name}`,'--yes']);
    console.log(JSON.stringify({name,image,deployRequested:true,mode:'live',paused:true}));
  } else if(action==='deploy-evidence-notes-code') {
    const name=process.argv[3];
    if(!names.slice(1).includes(name)) throw new Error('Only NicheRadar apps can be updated');
    const isDashboard=name==='nicheradar-dashboard';
    const before=cli(['app','inspect',`${project}/${name}`]);
    const env=appEnv(name);
    const expected=isDashboard?evidenceRelDashboard:name==='nicheradar-worker'?evidenceRelWorker:evidenceRelBackend;
    if(before.source?.image!==expected || before.ports?.length ||
       before.deploy?.replicas!==1 || before.resources?.memoryLimit!==512 ||
       env.NR_MODE!=='live' || env.NR_RADAR_PAUSED!=='true')
      throw new Error('Evidence notes release preconditions failed');
    const image=isDashboard?evidenceNotesDashboard:name==='nicheradar-worker'?evidenceNotesWorker:evidenceNotesBackend;
    cli(['app','update-source-image',`${project}/${name}`,'--yes'],{image});
    const after=cli(['app','inspect',`${project}/${name}`]);
    for(const field of ['env','resources','deploy','ports','mounts','basicAuth']) {
      if(JSON.stringify(before[field])!==JSON.stringify(after[field])) throw new Error('Unexpected configuration change; deployment not requested');
    }
    if(after.source?.image!==image) throw new Error('Image setting not persisted');
    cli(['app','deploy',`${project}/${name}`,'--yes']);
    console.log(JSON.stringify({name,image,deployRequested:true,mode:'live',paused:true}));
  } else if(action==='deploy-evidence-dollar-code') {
    const name=process.argv[3];
    if(!names.slice(1).includes(name)) throw new Error('Only NicheRadar apps can be updated');
    const isDashboard=name==='nicheradar-dashboard';
    const before=cli(['app','inspect',`${project}/${name}`]);
    const env=appEnv(name);
    const expected=isDashboard?evidenceNotesDashboard:name==='nicheradar-worker'?evidenceNotesWorker:evidenceNotesBackend;
    if(before.source?.image!==expected || before.ports?.length ||
       before.deploy?.replicas!==1 || before.resources?.memoryLimit!==512 ||
       env.NR_MODE!=='live' || env.NR_RADAR_PAUSED!=='true')
      throw new Error('Evidence dollar release preconditions failed');
    const image=isDashboard?evidenceDollarDashboard:name==='nicheradar-worker'?evidenceDollarWorker:evidenceDollarBackend;
    cli(['app','update-source-image',`${project}/${name}`,'--yes'],{image});
    const after=cli(['app','inspect',`${project}/${name}`]);
    for(const field of ['env','resources','deploy','ports','mounts','basicAuth']) {
      if(JSON.stringify(before[field])!==JSON.stringify(after[field])) throw new Error('Unexpected configuration change; deployment not requested');
    }
    if(after.source?.image!==image) throw new Error('Image setting not persisted');
    cli(['app','deploy',`${project}/${name}`,'--yes']);
    console.log(JSON.stringify({name,image,deployRequested:true,mode:'live',paused:true}));
  } else if(action==='deploy-evidence-rpm-code') {
    const name=process.argv[3];
    if(!names.slice(1).includes(name)) throw new Error('Only NicheRadar apps can be updated');
    const isDashboard=name==='nicheradar-dashboard';
    const before=cli(['app','inspect',`${project}/${name}`]);
    const env=appEnv(name);
    const expected=isDashboard?evidenceDollarDashboard:name==='nicheradar-worker'?evidenceDollarWorker:evidenceDollarBackend;
    if(before.source?.image!==expected || before.ports?.length ||
       before.deploy?.replicas!==1 || before.resources?.memoryLimit!==512 ||
       env.NR_MODE!=='live' || env.NR_RADAR_PAUSED!=='true')
      throw new Error('Evidence rpm release preconditions failed');
    const image=isDashboard?evidenceRpmDashboard:name==='nicheradar-worker'?evidenceRpmWorker:evidenceRpmBackend;
    cli(['app','update-source-image',`${project}/${name}`,'--yes'],{image});
    const after=cli(['app','inspect',`${project}/${name}`]);
    for(const field of ['env','resources','deploy','ports','mounts','basicAuth']) {
      if(JSON.stringify(before[field])!==JSON.stringify(after[field])) throw new Error('Unexpected configuration change; deployment not requested');
    }
    if(after.source?.image!==image) throw new Error('Image setting not persisted');
    cli(['app','deploy',`${project}/${name}`,'--yes']);
    console.log(JSON.stringify({name,image,deployRequested:true,mode:'live',paused:true}));
  } else if(action==='set-llm-limits') {
    // Tope del proveedor de LLM (semanal y mensual) en NR_LLM_CONFIGURATION del worker. Es el límite que
    // `reserve` aplica junto con el del perfil del radar (se usa el menor). Uso: set-llm-limits <semanal>
    // <mensual> [dry]. Con `dry` solo muestra los valores actuales. Nunca imprime la configuración.
    const name='nicheradar-worker';
    const week=Number(process.argv[3]), month=Number(process.argv[4]);
    if(!Number.isFinite(week) || !Number.isFinite(month) || week<5 || week>20 || month<week || month>30)
      throw new Error('Usage: set-llm-limits <weekly 5..20> <monthly weekly..30> [dry]');
    const before=cli(['app','inspect',`${project}/${name}`]);
    const env=appEnv(name);
    if(env.NR_MODE!=='live' || env.NR_RADAR_PAUSED!=='true') throw new Error('LLM limits preconditions failed');
    let configuration;
    try { configuration=JSON.parse(env.NR_LLM_CONFIGURATION); }
    catch { throw new Error('NR_LLM_CONFIGURATION is not valid JSON'); }
    const limits=configuration.limits;
    if(!limits || limits.week===undefined || limits.period===undefined) throw new Error('LLM limits are missing');
    const was={week:limits.week,period:limits.period};
    const set=(current,next)=>typeof current==='string'?String(next):next;
    configuration.limits={...limits,week:set(limits.week,week),period:set(limits.period,month)};
    const result={name,week:{before:was.week,after:configuration.limits.week},
      period:{before:was.period,after:configuration.limits.period},dryRun:process.argv[5]==='dry'};
    if(result.dryRun) {
      console.log(JSON.stringify(result));
    } else {
      const next={...env,NR_LLM_CONFIGURATION:JSON.stringify(configuration)};
      cli(['app','update-env',`${project}/${name}`,'--yes'],{env:Object.entries(next).map(([k,v])=>`${k}=${v}`).join('\n')});
      const after=cli(['app','inspect',`${project}/${name}`]);
      for(const field of ['source','resources','deploy','ports','mounts','basicAuth']) {
        if(JSON.stringify(before[field])!==JSON.stringify(after[field])) throw new Error('Unexpected non-environment change');
      }
      cli(['app','deploy',`${project}/${name}`,'--yes']);
      console.log(JSON.stringify({...result,deployRequested:true}));
    }
  } else if(action==='deploy-quality-rpm-code') {
    const name=process.argv[3];
    if(!names.slice(1).includes(name)) throw new Error('Only NicheRadar apps can be updated');
    const isDashboard=name==='nicheradar-dashboard';
    const before=cli(['app','inspect',`${project}/${name}`]);
    const env=appEnv(name);
    const expected=isDashboard?evidenceRpmDashboard:name==='nicheradar-worker'?evidenceRpmWorker:evidenceRpmBackend;
    if(before.source?.image!==expected || before.ports?.length ||
       before.deploy?.replicas!==1 || before.resources?.memoryLimit!==512 ||
       env.NR_MODE!=='live' || env.NR_RADAR_PAUSED!=='true')
      throw new Error('Quality rpm release preconditions failed');
    const image=isDashboard?qualityRpmDashboard:name==='nicheradar-worker'?qualityRpmWorker:qualityRpmBackend;
    cli(['app','update-source-image',`${project}/${name}`,'--yes'],{image});
    const after=cli(['app','inspect',`${project}/${name}`]);
    for(const field of ['env','resources','deploy','ports','mounts','basicAuth']) {
      if(JSON.stringify(before[field])!==JSON.stringify(after[field])) throw new Error('Unexpected configuration change; deployment not requested');
    }
    if(after.source?.image!==image) throw new Error('Image setting not persisted');
    cli(['app','deploy',`${project}/${name}`,'--yes']);
    console.log(JSON.stringify({name,image,deployRequested:true,mode:'live',paused:true}));
  } else if(action==='set-llm-limits') {
    // Tope del proveedor de LLM (semanal y mensual) en NR_LLM_CONFIGURATION del worker. Es el límite que
    // `reserve` aplica junto con el del perfil del radar (se usa el menor). Uso: set-llm-limits <semanal>
    // <mensual> [dry]. Con `dry` solo muestra los valores actuales. Nunca imprime la configuración.
    const name='nicheradar-worker';
    const week=Number(process.argv[3]), month=Number(process.argv[4]);
    if(!Number.isFinite(week) || !Number.isFinite(month) || week<5 || week>20 || month<week || month>30)
      throw new Error('Usage: set-llm-limits <weekly 5..20> <monthly weekly..30> [dry]');
    const before=cli(['app','inspect',`${project}/${name}`]);
    const env=appEnv(name);
    if(env.NR_MODE!=='live' || env.NR_RADAR_PAUSED!=='true') throw new Error('LLM limits preconditions failed');
    let configuration;
    try { configuration=JSON.parse(env.NR_LLM_CONFIGURATION); }
    catch { throw new Error('NR_LLM_CONFIGURATION is not valid JSON'); }
    const limits=configuration.limits;
    if(!limits || limits.week===undefined || limits.period===undefined) throw new Error('LLM limits are missing');
    const was={week:limits.week,period:limits.period};
    const set=(current,next)=>typeof current==='string'?String(next):next;
    configuration.limits={...limits,week:set(limits.week,week),period:set(limits.period,month)};
    const result={name,week:{before:was.week,after:configuration.limits.week},
      period:{before:was.period,after:configuration.limits.period},dryRun:process.argv[5]==='dry'};
    if(result.dryRun) {
      console.log(JSON.stringify(result));
    } else {
      const next={...env,NR_LLM_CONFIGURATION:JSON.stringify(configuration)};
      cli(['app','update-env',`${project}/${name}`,'--yes'],{env:Object.entries(next).map(([k,v])=>`${k}=${v}`).join('\n')});
      const after=cli(['app','inspect',`${project}/${name}`]);
      for(const field of ['source','resources','deploy','ports','mounts','basicAuth']) {
        if(JSON.stringify(before[field])!==JSON.stringify(after[field])) throw new Error('Unexpected non-environment change');
      }
      cli(['app','deploy',`${project}/${name}`,'--yes']);
      console.log(JSON.stringify({...result,deployRequested:true}));
    }
  } else if(action==='deploy-isolated-income-code') {
    const name=process.argv[3];
    if(!names.slice(1).includes(name)) throw new Error('Only NicheRadar apps can be updated');
    const isDashboard=name==='nicheradar-dashboard';
    const before=cli(['app','inspect',`${project}/${name}`]);
    const env=appEnv(name);
    const expected=isDashboard?qualityRpmDashboard:name==='nicheradar-worker'?qualityRpmWorker:qualityRpmBackend;
    if(before.source?.image!==expected || before.ports?.length ||
       before.deploy?.replicas!==1 || before.resources?.memoryLimit!==512 ||
       env.NR_MODE!=='live' || env.NR_RADAR_PAUSED!=='true')
      throw new Error('Isolated income release preconditions failed');
    const image=isDashboard?isolatedIncomeDashboard:name==='nicheradar-worker'?isolatedIncomeWorker:isolatedIncomeBackend;
    cli(['app','update-source-image',`${project}/${name}`,'--yes'],{image});
    const after=cli(['app','inspect',`${project}/${name}`]);
    for(const field of ['env','resources','deploy','ports','mounts','basicAuth']) {
      if(JSON.stringify(before[field])!==JSON.stringify(after[field])) throw new Error('Unexpected configuration change; deployment not requested');
    }
    if(after.source?.image!==image) throw new Error('Image setting not persisted');
    cli(['app','deploy',`${project}/${name}`,'--yes']);
    console.log(JSON.stringify({name,image,deployRequested:true,mode:'live',paused:true}));
  } else if(action==='set-llm-limits') {
    // Tope del proveedor de LLM (semanal y mensual) en NR_LLM_CONFIGURATION del worker. Es el límite que
    // `reserve` aplica junto con el del perfil del radar (se usa el menor). Uso: set-llm-limits <semanal>
    // <mensual> [dry]. Con `dry` solo muestra los valores actuales. Nunca imprime la configuración.
    const name='nicheradar-worker';
    const week=Number(process.argv[3]), month=Number(process.argv[4]);
    if(!Number.isFinite(week) || !Number.isFinite(month) || week<5 || week>20 || month<week || month>30)
      throw new Error('Usage: set-llm-limits <weekly 5..20> <monthly weekly..30> [dry]');
    const before=cli(['app','inspect',`${project}/${name}`]);
    const env=appEnv(name);
    if(env.NR_MODE!=='live' || env.NR_RADAR_PAUSED!=='true') throw new Error('LLM limits preconditions failed');
    let configuration;
    try { configuration=JSON.parse(env.NR_LLM_CONFIGURATION); }
    catch { throw new Error('NR_LLM_CONFIGURATION is not valid JSON'); }
    const limits=configuration.limits;
    if(!limits || limits.week===undefined || limits.period===undefined) throw new Error('LLM limits are missing');
    const was={week:limits.week,period:limits.period};
    const set=(current,next)=>typeof current==='string'?String(next):next;
    configuration.limits={...limits,week:set(limits.week,week),period:set(limits.period,month)};
    const result={name,week:{before:was.week,after:configuration.limits.week},
      period:{before:was.period,after:configuration.limits.period},dryRun:process.argv[5]==='dry'};
    if(result.dryRun) {
      console.log(JSON.stringify(result));
    } else {
      const next={...env,NR_LLM_CONFIGURATION:JSON.stringify(configuration)};
      cli(['app','update-env',`${project}/${name}`,'--yes'],{env:Object.entries(next).map(([k,v])=>`${k}=${v}`).join('\n')});
      const after=cli(['app','inspect',`${project}/${name}`]);
      for(const field of ['source','resources','deploy','ports','mounts','basicAuth']) {
        if(JSON.stringify(before[field])!==JSON.stringify(after[field])) throw new Error('Unexpected non-environment change');
      }
      cli(['app','deploy',`${project}/${name}`,'--yes']);
      console.log(JSON.stringify({...result,deployRequested:true}));
    }
  } else if(action==='set-evidence-cap') {
    // Solo el worker corre el scraper. Fija cuántas fichas lee la etapa evidence por corrida
    // (0 la apaga). Decisión del propietario: piloto de 100 y luego ampliar (2026-10-28).
    const name='nicheradar-worker';
    const cap=Number(process.argv[3]);
    if(!Number.isInteger(cap) || cap<0 || cap>500) throw new Error('Cap must be an integer from 0 to 500');
    const before=cli(['app','inspect',`${project}/${name}`]);
    const env=appEnv(name);
    if(env.NR_MODE!=='live' || before.source?.image!==isolatedIncomeWorker) throw new Error('Evidence cap preconditions failed');
    const next={...env,NR_MARKET_INTEL_EVIDENCE_CAP_PER_RUN:String(cap)};
    cli(['app','update-env',`${project}/${name}`,'--yes'],{env:Object.entries(next).map(([k,v])=>`${k}=${v}`).join('\n')});
    const after=cli(['app','inspect',`${project}/${name}`]);
    for(const field of ['source','resources','deploy','ports','mounts','basicAuth']) {
      if(JSON.stringify(before[field])!==JSON.stringify(after[field])) throw new Error('Unexpected non-environment change');
    }
    cli(['app','deploy',`${project}/${name}`,'--yes']);
    console.log(JSON.stringify({name,evidenceCap:next.NR_MARKET_INTEL_EVIDENCE_CAP_PER_RUN,deployRequested:true}));
  } else if(action==='set-youtube-enrich-caps') {
    // Solo el worker corre el scraper. Sube (nunca baja) los topes de la etapa enrich y la cuota
    // de detalle de YouTube que comparte con verify (decisión del propietario, 2026-10-28).
    const name='nicheradar-worker';
    const before=cli(['app','inspect',`${project}/${name}`]);
    const env=appEnv(name);
    if(env.NR_MODE!=='live' || before.source?.image!==enrichWorker) throw new Error('Enrich caps preconditions failed');
    const want={NR_MARKET_INTEL_ENRICH_CAP_PER_RUN:500,NR_YOUTUBE_DETAIL_QUOTA_PER_RUN:1500,
      NR_YOUTUBE_DETAIL_QUOTA_PER_WEEK:12000,NR_YOUTUBE_DETAIL_QUOTA_PER_MONTH:30000};
    const next={...env};
    for(const [key,value] of Object.entries(want)) next[key]=String(Math.max(Number(env[key]??0),value));
    cli(['app','update-env',`${project}/${name}`,'--yes'],{env:Object.entries(next).map(([k,v])=>`${k}=${v}`).join('\n')});
    const after=cli(['app','inspect',`${project}/${name}`]);
    for(const field of ['source','resources','deploy','ports','mounts','basicAuth']) {
      if(JSON.stringify(before[field])!==JSON.stringify(after[field])) throw new Error('Unexpected non-environment change');
    }
    cli(['app','deploy',`${project}/${name}`,'--yes']);
    console.log(JSON.stringify({name,enrichCap:next.NR_MARKET_INTEL_ENRICH_CAP_PER_RUN,quotaRun:next.NR_YOUTUBE_DETAIL_QUOTA_PER_RUN,quotaWeek:next.NR_YOUTUBE_DETAIL_QUOTA_PER_WEEK,quotaMonth:next.NR_YOUTUBE_DETAIL_QUOTA_PER_MONTH,deployRequested:true}));
  } else if(action==='deploy-channel-analysis-insights-code') {
    const name=process.argv[3];
    if(!names.slice(1).includes(name)) throw new Error('Only NicheRadar apps can be updated');
    const isDashboard=name==='nicheradar-dashboard';
    const before=cli(['app','inspect',`${project}/${name}`]);
    const env=appEnv(name);
    const expected=isDashboard?channelAnalysisDashboard:name==='nicheradar-worker'?channelAnalysisWorker:channelAnalysisBackend;
    if(before.source?.image!==expected || before.ports?.length ||
       before.deploy?.replicas!==1 || before.resources?.memoryLimit!==512 ||
       env.NR_MODE!=='live' || env.NR_RADAR_PAUSED!=='true')
      throw new Error('Channel analysis insights release preconditions failed');
    const image=isDashboard?insightsScoreDashboard:name==='nicheradar-worker'?insightsScoreWorker:insightsScoreBackend;
    cli(['app','update-source-image',`${project}/${name}`,'--yes'],{image});
    const after=cli(['app','inspect',`${project}/${name}`]);
    for(const field of ['env','resources','deploy','ports','mounts','basicAuth']) {
      if(JSON.stringify(before[field])!==JSON.stringify(after[field])) throw new Error('Unexpected configuration change; deployment not requested');
    }
    if(after.source?.image!==image) throw new Error('Image setting not persisted');
    cli(['app','deploy',`${project}/${name}`,'--yes']);
    console.log(JSON.stringify({name,image,deployRequested:true,mode:'live',paused:true}));
  } else if(action==='deploy-channel-analysis-code') {
    const name=process.argv[3];
    if(!names.slice(1).includes(name)) throw new Error('Only NicheRadar apps can be updated');
    const isDashboard=name==='nicheradar-dashboard';
    const before=cli(['app','inspect',`${project}/${name}`]);
    const env=appEnv(name);
    const expected=isDashboard?homeProfitDashboard:name==='nicheradar-worker'?homeProfitWorker:homeProfitBackend;
    if(before.source?.image!==expected || before.ports?.length ||
       before.deploy?.replicas!==1 || before.resources?.memoryLimit!==512 ||
       env.NR_MODE!=='live' || env.NR_RADAR_PAUSED!=='true')
      throw new Error('Channel analysis release preconditions failed');
    const image=isDashboard?channelAnalysisDashboard:name==='nicheradar-worker'?channelAnalysisWorker:channelAnalysisBackend;
    cli(['app','update-source-image',`${project}/${name}`,'--yes'],{image});
    const after=cli(['app','inspect',`${project}/${name}`]);
    for(const field of ['env','resources','deploy','ports','mounts','basicAuth']) {
      if(JSON.stringify(before[field])!==JSON.stringify(after[field])) throw new Error('Unexpected configuration change; deployment not requested');
    }
    if(after.source?.image!==image) throw new Error('Image setting not persisted');
    cli(['app','deploy',`${project}/${name}`,'--yes']);
    console.log(JSON.stringify({name,image,deployRequested:true,mode:'live',paused:true}));
  } else if(action==='deploy-default-recipe-code') {
    const name=process.argv[3];
    if(!names.slice(1).includes(name)) throw new Error('Only NicheRadar apps can be updated');
    const isDashboard=name==='nicheradar-dashboard';
    const before=cli(['app','inspect',`${project}/${name}`]);
    const env=appEnv(name);
    const expected=isDashboard?jsonCleanupDashboard:name==='nicheradar-worker'?jsonCleanupWorker:jsonCleanupBackend;
    if(before.source?.image!==expected || before.ports?.length ||
       before.deploy?.replicas!==1 || before.resources?.memoryLimit!==512 ||
       env.NR_MODE!=='live' || env.NR_RADAR_PAUSED!=='true')
      throw new Error('Default recipe release preconditions failed');
    const image=isDashboard?defaultRecipeDashboard:name==='nicheradar-worker'?defaultRecipeWorker:defaultRecipeBackend;
    cli(['app','update-source-image',`${project}/${name}`,'--yes'],{image});
    const after=cli(['app','inspect',`${project}/${name}`]);
    for(const field of ['env','resources','deploy','ports','mounts','basicAuth']) {
      if(JSON.stringify(before[field])!==JSON.stringify(after[field])) throw new Error('Unexpected configuration change; deployment not requested');
    }
    if(after.source?.image!==image) throw new Error('Image setting not persisted');
    cli(['app','deploy',`${project}/${name}`,'--yes']);
    console.log(JSON.stringify({name,image,deployRequested:true,mode:'live',paused:true}));
  } else if(action==='deploy-home-profit-code') {
    const name=process.argv[3];
    if(!names.slice(1).includes(name)) throw new Error('Only NicheRadar apps can be updated');
    const isDashboard=name==='nicheradar-dashboard';
    const before=cli(['app','inspect',`${project}/${name}`]);
    const env=appEnv(name);
    const expected=isDashboard?defaultRecipeDashboard:name==='nicheradar-worker'?defaultRecipeWorker:defaultRecipeBackend;
    if(before.source?.image!==expected || before.ports?.length ||
       before.deploy?.replicas!==1 || before.resources?.memoryLimit!==512 ||
       env.NR_MODE!=='live' || env.NR_RADAR_PAUSED!=='true')
      throw new Error('Home/profit release preconditions failed');
    const image=isDashboard?homeProfitDashboard:name==='nicheradar-worker'?homeProfitWorker:homeProfitBackend;
    cli(['app','update-source-image',`${project}/${name}`,'--yes'],{image});
    const after=cli(['app','inspect',`${project}/${name}`]);
    for(const field of ['env','resources','deploy','ports','mounts','basicAuth']) {
      if(JSON.stringify(before[field])!==JSON.stringify(after[field])) throw new Error('Unexpected configuration change; deployment not requested');
    }
    if(after.source?.image!==image) throw new Error('Image setting not persisted');
    cli(['app','deploy',`${project}/${name}`,'--yes']);
    console.log(JSON.stringify({name,image,deployRequested:true,mode:'live',paused:true}));
  } else if(action==='set-batch-size') {
    const value=Number(process.argv[3]);
    if(!Number.isInteger(value) || value<1 || value>10000) throw new Error('batch size must be an integer between 1 and 10000');
    const name='nicheradar-worker';
    const before=cli(['app','inspect',`${project}/${name}`]);
    const env=appEnv(name);
    if(before.source?.image!==insightsScoreWorker || env.NR_MODE!=='live' || env.NR_RADAR_PAUSED!=='true')
      throw new Error('Batch size configuration preconditions failed');
    cli(['app','update-env',`${project}/${name}`,'--yes'],{
      env:Object.entries({...env,NR_BATCH_SIZE:String(value)}).map(([key,val])=>`${key}=${val}`).join('\n')});
    const after=cli(['app','inspect',`${project}/${name}`]);
    for(const field of ['source','resources','deploy','ports','mounts','basicAuth']) {
      if(JSON.stringify(before[field])!==JSON.stringify(after[field])) throw new Error('Unexpected non-environment change');
    }
    cli(['app','deploy',`${project}/${name}`,'--yes']);
    console.log(JSON.stringify({name,batchSize:value,configured:true,mode:'live',paused:true}));
  } else if(action==='configure-youtube-paused') {
    const youtube=localYouTubeConfig();
    for(const name of ['nicheradar-api','nicheradar-worker']) {
      const before=cli(['app','inspect',`${project}/${name}`]);
      const env=appEnv(name);
      const expected=name==='nicheradar-worker'?jsonCleanupWorker:jsonCleanupBackend;
      if(before.source?.image!==expected || env.NR_MODE!=='live' || env.NR_RADAR_PAUSED!=='true' ||
         !env.NR_VIDIQ_TOKEN || env.NR_VIDIQ_LIVE_ENABLED!=='true' ||
         (env.NR_YOUTUBE_API_KEY && env.NR_YOUTUBE_API_KEY!==youtube.NR_YOUTUBE_API_KEY))
        throw new Error('YouTube configuration preconditions failed');
      cli(['app','update-env',`${project}/${name}`,'--yes'],{
        env:Object.entries({...env,...youtube}).map(([key,value])=>`${key}=${value}`).join('\n')});
      const after=cli(['app','inspect',`${project}/${name}`]);
      for(const field of ['source','resources','deploy','ports','mounts','basicAuth']) {
        if(JSON.stringify(before[field])!==JSON.stringify(after[field])) throw new Error('Unexpected non-environment change');
      }
      cli(['app','deploy',`${project}/${name}`,'--yes']);
      console.log(JSON.stringify({name,configured:true,mode:'live',paused:true,youtubeEnabled:true}));
    }
  } else if(action==='configure-llm-paused') {
    const llm=localLLMConfig();
    for(const name of ['nicheradar-api','nicheradar-worker']) {
      const before=cli(['app','inspect',`${project}/${name}`]);
      const env=appEnv(name);
      const expected=name==='nicheradar-worker'?jsonCleanupWorker:jsonCleanupBackend;
      if(before.source?.image!==expected || env.NR_MODE!=='live' || env.NR_RADAR_PAUSED!=='true' ||
         !env.NR_VIDIQ_TOKEN || env.NR_VIDIQ_LIVE_ENABLED!=='true' ||
         (env.NR_LLM_API_KEY && env.NR_LLM_API_KEY!==llm.NR_LLM_API_KEY))
        throw new Error('LLM configuration preconditions failed');
      cli(['app','update-env',`${project}/${name}`,'--yes'],{
        env:Object.entries({...env,...llm}).map(([key,value])=>`${key}=${value}`).join('\n')});
      const after=cli(['app','inspect',`${project}/${name}`]);
      for(const field of ['source','resources','deploy','ports','mounts','basicAuth']) {
        if(JSON.stringify(before[field])!==JSON.stringify(after[field])) throw new Error('Unexpected non-environment change');
      }
      cli(['app','deploy',`${project}/${name}`,'--yes']);
      console.log(JSON.stringify({name,configured:true,mode:'live',paused:true,llmEnabled:true}));
    }
  } else if(action==='create-db') {
    if(inventory().some(s=>s.name==='nicheradar-db')) throw new Error('Database already exists; will not overwrite');
    cli(['postgres','create',`${project}/nicheradar-db`],{
      image:postgres,databaseName:'nicheradar',user:'postgres',password:secret(),
      env:'PGDATA=/var/lib/postgresql/data/pgdata\nPOSTGRES_HOST_AUTH_METHOD=scram-sha-256',
      resources:resources(0.5),pgWeb:{enabled:false},dbGate:{enabled:false},
    });
    summarize('postgres','nicheradar-db');
  } else if(action==='configure-db-limits') {
    if(!inventory().some(s=>s.name==='nicheradar-db' && s.type==='postgres')) throw new Error('Database missing');
    cli(['postgres','update-resources',`${project}/nicheradar-db`,'--yes'],{resources:resources(0.5)});
    console.log('Database resource settings updated; verify Docker effective limits separately.');
  } else if(action==='migrate') {
    const env=appEnv('nicheradar-api');
    if(env.NR_DATABASE_URL!==dbURL() || env.NR_MODE!=='synthetic' || env.NR_RADAR_PAUSED!=='true') throw new Error('Migration preconditions failed');
    const code='import json,os,subprocess,sys; os.environ.update(json.load(sys.stdin)); sys.exit(subprocess.call(["alembic","upgrade","head"]))';
    const args=['docker','run','--rm','-i','--name','nicheradar-migration-20260915-001',
      '--network','easypanel-proy1-credito-riesgo','--memory','512m','--cpus','1',
      '--read-only','--tmpfs','/tmp:rw,noexec,nosuid,size=64m','--cap-drop','ALL',
      '--security-opt','no-new-privileges',backend,'python','-c',code];
    const result=spawnSync('ssh',[...sshArgs,args.map(quote).join(' ')],{
      input:JSON.stringify({NR_DATABASE_URL:env.NR_DATABASE_URL,NR_MODE:'synthetic',NR_RADAR_PAUSED:'true'}),
      encoding:'utf8',timeout:180000,maxBuffer:1024*1024});
    console.log(JSON.stringify({migrationExit:result.status,processError:result.error?.code ?? null}));
    if(result.error || result.status!==0) throw new Error('Migration failed; raw response withheld. Inspect only this migration safely.');
  } else if(action==='start-apps') {
    for(const name of names.slice(1)) {
      const s=cli(['app','inspect',`${project}/${name}`]);
      const env=appEnv(name);
      if(s.source?.image!==(name==='nicheradar-dashboard'?dashboard:backend) || s.domains?.length || s.ports?.length ||
        env.NR_MODE!=='synthetic' || env.NR_RADAR_PAUSED!=='true') throw new Error('App start preconditions failed');
      cli(['app','update-deploy',`${project}/${name}`,'--yes'],{deploy:{replicas:1,command:name,zeroDowntime:false}});
      cli(['app','deploy',`${project}/${name}`,'--yes']);
      console.log(JSON.stringify({name,deployRequested:true}));
    }
  } else if(action==='probe') {
    const mode=process.argv[3] ?? 'check';
    if(!['check','ui','monitoring','set-marker','verify-restore'].includes(mode)) throw new Error('Invalid probe mode');
    const query=spawnSync('ssh',[...sshArgs,'docker ps --filter label=com.docker.swarm.service.name=proy1-credito-riesgo_nicheradar-dashboard --format "{{.ID}}"'],{encoding:'utf8',timeout:20000});
    const cid=query.stdout?.trim();
    if(query.status!==0 || !/^[a-f0-9]{12}$/.test(cid)) throw new Error('Exactly one dashboard container required');
    const result=spawnSync('ssh',[...sshArgs,`docker exec -i ${cid} python - ${mode}`],{
      input:readFileSync(new URL('./easypanel_probe.py',import.meta.url)),encoding:'utf8',timeout:120000,maxBuffer:1024*1024});
    for(const line of (result.stdout ?? '').split('\n')) {
      if(/^(api_auth_ok |dashboard_view_ok |dashboard_login_verified$|monitoring_fixture_verified |profile_marker_saved$|persistence_verified_profile_restored$|probe_failed )/.test(line)) console.log(line);
    }
    if(result.error || result.status!==0) throw new Error(`Probe failed (exit ${result.status}); other output withheld`);
  } else if(action==='activate-live-db') {
    const query=spawnSync('ssh',[...sshArgs,'docker ps --filter label=com.docker.swarm.service.name=proy1-credito-riesgo_nicheradar-api --format "{{.ID}}"'],{encoding:'utf8',timeout:20000});
    const cid=query.stdout?.trim();
    if(query.status!==0 || !/^[a-f0-9]{12}$/.test(cid)) throw new Error('Exactly one API container required');
    const result=spawnSync('ssh',[...sshArgs,`docker exec -i ${cid} python -`],{
      input:readFileSync(new URL('./activate_live.py',import.meta.url)),encoding:'utf8',timeout:120000,maxBuffer:1024*1024});
    if(result.error || result.status!==0) throw new Error(`Live DB activation failed (exit ${result.status}); output withheld`);
    const parsed=JSON.parse(result.stdout);
    console.log(JSON.stringify(parsed));
  } else if(action==='seed-niche-match-policy') {
    const query=spawnSync('ssh',[...sshArgs,'docker ps --filter label=com.docker.swarm.service.name=proy1-credito-riesgo_nicheradar-api --format "{{.ID}}"'],{encoding:'utf8',timeout:20000});
    const cid=query.stdout?.trim();
    if(query.status!==0 || !/^[a-f0-9]{12}$/.test(cid)) throw new Error('Exactly one API container required');
    const result=spawnSync('ssh',[...sshArgs,`docker exec -i ${cid} python -`],{
      input:readFileSync(new URL('./seed_niche_match_policy.py',import.meta.url)),encoding:'utf8',timeout:60000,maxBuffer:1024*1024});
    if(result.error || result.status!==0) throw new Error(`Niche match policy seed failed (exit ${result.status}); output withheld`);
    console.log(JSON.stringify(JSON.parse(result.stdout)));
  } else if(action==='set-radar-paused') {
    const value=process.argv[3];
    if(value!=='true' && value!=='false') throw new Error('pass true or false');
    const query=spawnSync('ssh',[...sshArgs,'docker ps --filter label=com.docker.swarm.service.name=proy1-credito-riesgo_nicheradar-dashboard --format "{{.ID}}"'],{encoding:'utf8',timeout:20000});
    const cid=query.stdout?.trim();
    if(query.status!==0 || !/^[a-f0-9]{12}$/.test(cid)) throw new Error('Exactly one dashboard container required');
    const args=['docker','exec','-i',cid,'python','-',value].map(quote).join(' ');
    const code=`
import json, os, sys
import httpx
base = os.environ["NR_API_URL"].rstrip("/") + "/api/v1"
headers = {"Authorization": f"Bearer {os.environ['NR_SERVICE_TOKEN']}"}
r = httpx.request("PUT", base + "/radar", json={"paused": sys.argv[1] == "true"}, headers=headers, timeout=15)
if r.status_code >= 400: raise SystemExit(f"{r.status_code}: {r.text}")
print(json.dumps(r.json()))
`;
    const result=spawnSync('ssh',[...sshArgs,args],{input:code,encoding:'utf8',timeout:30000,maxBuffer:1024*1024});
    if(result.error || result.status!==0) throw new Error(`Radar pause toggle failed (exit ${result.status}); stderr: ${result.stderr}`);
    console.log(result.stdout.trim());
  } else if(action==='run-scheduled-once') {
    const query=spawnSync('ssh',[...sshArgs,'docker ps --filter label=com.docker.swarm.service.name=proy1-credito-riesgo_nicheradar-dashboard --format "{{.ID}}"'],{encoding:'utf8',timeout:20000});
    const cid=query.stdout?.trim();
    if(query.status!==0 || !/^[a-f0-9]{12}$/.test(cid)) throw new Error('Exactly one dashboard container required');
    const result=spawnSync('ssh',[...sshArgs,`docker exec -i ${cid} python -`],{
      input:readFileSync(new URL('./run_scheduled_once.py',import.meta.url)),encoding:'utf8',timeout:300000,maxBuffer:1024*1024});
    if(result.error || result.status!==0) throw new Error(`Scheduled observation failed (exit ${result.status}); output withheld; verify pause immediately`);
    console.log(JSON.stringify(JSON.parse(result.stdout)));
  } else if(action==='test-channel-analysis') {
    const channelInput=process.argv[3];
    if(!channelInput) throw new Error('A channel_input argument is required');
    // The api container, not dashboard: test_channel_analysis.py's defer_due_radar_schedule()
    // needs direct NR_DATABASE_URL access, which only the api/worker containers have.
    const query=spawnSync('ssh',[...sshArgs,'docker ps --filter label=com.docker.swarm.service.name=proy1-credito-riesgo_nicheradar-api --format "{{.ID}}"'],{encoding:'utf8',timeout:20000});
    const cid=query.stdout?.trim();
    if(query.status!==0 || !/^[a-f0-9]{12}$/.test(cid)) throw new Error('Exactly one api container required');
    const args=['docker','exec','-i',cid,'python','-',channelInput].map(quote).join(' ');
    const result=spawnSync('ssh',[...sshArgs,args],{
      input:readFileSync(new URL('./test_channel_analysis.py',import.meta.url)),encoding:'utf8',timeout:450000,maxBuffer:1024*1024});
    if(result.error || result.status!==0) throw new Error(`Channel analysis test failed (exit ${result.status}); verify pause immediately; stderr: ${result.stderr}`);
    console.log(JSON.stringify(JSON.parse(result.stdout)));
  } else if(action==='scheduled-evidence') {
    const offset=process.argv[3] ?? '0';
    if(!/^(?:[0-9]|1[0-9]|20)$/.test(offset)) throw new Error('Invalid scheduled evidence offset');
    const query=spawnSync('ssh',[...sshArgs,'docker ps --filter label=com.docker.swarm.service.name=proy1-credito-riesgo_nicheradar-api --format "{{.ID}}"'],{encoding:'utf8',timeout:20000});
    const cid=query.stdout?.trim();
    if(query.status!==0 || !/^[a-f0-9]{12}$/.test(cid)) throw new Error('Exactly one API container required');
    const result=spawnSync('ssh',[...sshArgs,`docker exec -i ${cid} python - ${offset}`],{
      input:readFileSync(new URL('./read_scheduled_evidence.py',import.meta.url)),encoding:'utf8',timeout:120000,maxBuffer:1024*1024});
    if(result.error || result.status!==0) throw new Error(`Scheduled evidence failed (exit ${result.status}); output withheld`);
    console.log(JSON.stringify(JSON.parse(result.stdout)));
  } else if(action==='read-flow-research-state') {
    const query=spawnSync('ssh',[...sshArgs,'docker ps --filter label=com.docker.swarm.service.name=proy1-credito-riesgo_nicheradar-api --format "{{.ID}}"'],{encoding:'utf8',timeout:20000});
    const cid=query.stdout?.trim();
    if(query.status!==0 || !/^[a-f0-9]{12}$/.test(cid)) throw new Error('Exactly one API container required');
    const result=spawnSync('ssh',[...sshArgs,`docker exec -i ${cid} python -`],{
      input:readFileSync(new URL('./read_flow_research_state.py',import.meta.url)),encoding:'utf8',timeout:60000,maxBuffer:1024*1024});
    if(result.error || result.status!==0) throw new Error(`Flow research state read failed (exit ${result.status}); output withheld`);
    console.log(JSON.stringify(JSON.parse(result.stdout)));
  } else if(action==='delete-legacy-flow-request') {
    const expected=process.argv[3];
    if(!/^[0-9]$/.test(expected ?? '')) throw new Error('Expected row count (0-9) required');
    const query=spawnSync('ssh',[...sshArgs,'docker ps --filter label=com.docker.swarm.service.name=proy1-credito-riesgo_nicheradar-api --format "{{.ID}}"'],{encoding:'utf8',timeout:20000});
    const cid=query.stdout?.trim();
    if(query.status!==0 || !/^[a-f0-9]{12}$/.test(cid)) throw new Error('Exactly one API container required');
    const result=spawnSync('ssh',[...sshArgs,`docker exec -i ${cid} python - ${expected}`],{
      input:readFileSync(new URL('./delete_legacy_flow_request.py',import.meta.url)),encoding:'utf8',timeout:60000,maxBuffer:1024*1024});
    if(result.error || result.status!==0) throw new Error(`Legacy flow request cleanup failed (exit ${result.status}); output withheld`);
    console.log(JSON.stringify(JSON.parse(result.stdout)));
  } else if(action==='read-llm-enrichment') {
    const query=spawnSync('ssh',[...sshArgs,'docker ps --filter label=com.docker.swarm.service.name=proy1-credito-riesgo_nicheradar-api --format "{{.ID}}"'],{encoding:'utf8',timeout:20000});
    const cid=query.stdout?.trim();
    if(query.status!==0 || !/^[a-f0-9]{12}$/.test(cid)) throw new Error('Exactly one API container required');
    const result=spawnSync('ssh',[...sshArgs,`docker exec -i ${cid} python -`],{
      input:readFileSync(new URL('./read_llm_enrichment.py',import.meta.url)),encoding:'utf8',timeout:120000,maxBuffer:1024*1024});
    if(result.error || result.status!==0) throw new Error(`LLM enrichment read failed (exit ${result.status}); output withheld`);
    console.log(JSON.stringify(JSON.parse(result.stdout)));
  } else if(action==='read-channel-analysis') {
    const analysisId=process.argv[3];
    if(!analysisId) throw new Error('An analysis id argument is required');
    const query=spawnSync('ssh',[...sshArgs,'docker ps --filter label=com.docker.swarm.service.name=proy1-credito-riesgo_nicheradar-api --format "{{.ID}}"'],{encoding:'utf8',timeout:20000});
    const cid=query.stdout?.trim();
    if(query.status!==0 || !/^[a-f0-9]{12}$/.test(cid)) throw new Error('Exactly one API container required');
    const args=['docker','exec','-i',cid,'python','-',analysisId].map(quote).join(' ');
    const result=spawnSync('ssh',[...sshArgs,args],{
      input:readFileSync(new URL('./read_channel_analysis.py',import.meta.url)),encoding:'utf8',timeout:120000,maxBuffer:1024*1024});
    if(result.error || result.status!==0) throw new Error(`Channel analysis read failed (exit ${result.status}); stderr: ${result.stderr}`);
    console.log(JSON.stringify(JSON.parse(result.stdout)));
  } else if(action==='read-backlog-ranking') {
    const query=spawnSync('ssh',[...sshArgs,'docker ps --filter label=com.docker.swarm.service.name=proy1-credito-riesgo_nicheradar-api --format "{{.ID}}"'],{encoding:'utf8',timeout:20000});
    const cid=query.stdout?.trim();
    if(query.status!==0 || !/^[a-f0-9]{12}$/.test(cid)) throw new Error('Exactly one API container required');
    const result=spawnSync('ssh',[...sshArgs,`docker exec -i ${cid} python -`],{
      input:readFileSync(new URL('./read_backlog_ranking.py',import.meta.url)),encoding:'utf8',timeout:120000,maxBuffer:1024*1024});
    if(result.error || result.status!==0) throw new Error(`Backlog ranking read failed (exit ${result.status}); output withheld`);
    console.log(JSON.stringify(JSON.parse(result.stdout)));
  } else if(action==='compute-references') {
    const query=spawnSync('ssh',[...sshArgs,'docker ps --filter label=com.docker.swarm.service.name=proy1-credito-riesgo_nicheradar-api --format "{{.ID}}"'],{encoding:'utf8',timeout:20000});
    const cid=query.stdout?.trim();
    if(query.status!==0 || !/^[a-f0-9]{12}$/.test(cid)) throw new Error('Exactly one API container required');
    const result=spawnSync('ssh',[...sshArgs,`docker exec -i ${cid} python -`],{
      input:readFileSync(new URL('./compute_references.py',import.meta.url)),encoding:'utf8',timeout:120000,maxBuffer:1024*1024});
    if(result.error || result.status!==0) throw new Error(`References computation failed (exit ${result.status}); output withheld`);
    console.log(JSON.stringify(JSON.parse(result.stdout)));
  } else if(action==='rollouts') {
    const services=names.slice(1).map(name=>`${project}_${name}`);
    const format='{{.Spec.Name}}|{{.UpdateStatus.State}}|{{.Spec.TaskTemplate.ContainerSpec.Image}}';
    const command=['docker','service','inspect','--format',format,...services]
      .map(quote).join(' ');
    const result=spawnSync('ssh',[...sshArgs,command],{
      encoding:'utf8',timeout:20000,maxBuffer:1024*1024});
    if(result.error || result.status!==0) throw new Error('Rollout inspection failed; output withheld');
    const rows=result.stdout.trim().split('\n').map(line=>{
      const [name,state,image]=line.split('|');
      if(!services.includes(name) || state!=='completed' || !image?.includes('@sha256:'))
        throw new Error('A rollout is not complete');
      return {name,state,image};
    });
    console.log(JSON.stringify({rollouts:rows}));
  } else if(action==='benchmark-live-relevance') {
    const env=appEnv('nicheradar-api');
    if(env.NR_MODE!=='live' || env.NR_RADAR_PAUSED!=='true' || !env.NR_DATABASE_URL)
      throw new Error('Live relevance benchmark preconditions failed');
    const code=readFileSync(new URL('./benchmark_live_relevance.py',import.meta.url),'utf8');
    const args=['docker','run','--rm','-i','--network','easypanel-proy1-credito-riesgo',
      '--memory','512m','--cpus','1','--read-only','--tmpfs','/tmp:rw,noexec,nosuid,size=64m',
      '--cap-drop','ALL','--security-opt','no-new-privileges',calibrationWorker,'python','-c',code];
    const result=spawnSync('ssh',[...sshArgs,args.map(quote).join(' ')],{
      input:JSON.stringify({NR_DATABASE_URL:env.NR_DATABASE_URL,NR_MODE:'live',NR_RADAR_PAUSED:'true'}),
      encoding:'utf8',timeout:300000,maxBuffer:1024*1024});
    if(result.error || result.status!==0) throw new Error(`Live relevance benchmark failed (exit ${result.status}); output withheld`);
    const lines=result.stdout.trim().split('\n');
    console.log(JSON.stringify(JSON.parse(lines.at(-1))));
  } else if(action==='restart-apps') {
    for(const name of names.slice(1)) {
      cli(['app','restart',`${project}/${name}`,'--yes']);
      console.log(JSON.stringify({name,restartRequested:true}));
    }
  } else if(action==='refresh-domain') {
    const matches=cli(['domains','list']).filter(d=>d.host==='nicheradar.soydavidrodriguez.com');
    if(matches.length!==1) throw new Error('Exactly one NicheRadar domain required');
    const d=matches[0];
    const dst=d.serviceDestination;
    if(!d.https || d.wildcard || d.path!=='/' || d.destinationType!=='service' ||
      dst?.projectName!==project || dst.serviceName!=='nicheradar-dashboard' ||
      dst.protocol!=='http' || dst.port!==8501 || (d.middlewares??[]).length ||
      !['','letsencrypt'].includes(d.certificateResolver)) throw new Error('Unexpected domain configuration');
    const s=cli(['app','inspect',`${project}/nicheradar-dashboard`]);
    if(!s.basicAuth?.length || s.ports?.length) throw new Error('Dashboard protection precondition failed');
    cli(['domains','update','--yes'],{id:d.id,host:d.host,path:d.path,https:true,wildcard:false,
      certificateResolver:'letsencrypt',middlewares:[],destinationType:'service',serviceDestination:dst});
    console.log('NicheRadar domain saved with explicit existing letsencrypt resolver; HTTPS and auth preserved.');
  } else if(action==='create-domain') {
    const host='nicheradar.soydavidrodriguez.com';
    const s=cli(['app','inspect',`${project}/nicheradar-dashboard`]);
    if(!s.basicAuth?.length || s.ports?.length) throw new Error('Dashboard auth or ports precondition failed');
    const domains=cli(['domains','list']);
    if(!Array.isArray(domains) || domains.some(d=>d.host===host)) throw new Error('Domain inventory invalid or hostname already configured');
    cli(['domains','create'],{id:randomUUID(),host,path:'/',https:true,wildcard:false,certificateResolver:'',middlewares:[],
      destinationType:'service',serviceDestination:{projectName:project,serviceName:'nicheradar-dashboard',protocol:'http',port:8501,path:'/'}});
    console.log(JSON.stringify({domain:host,httpsConfigured:true,dnsAndCertificateVerificationPending:true}));
  } else if(action==='create-apps') {
    const existing=inventory();
    if(existing.some(s=>names.slice(1).includes(s.name))) throw new Error('One or more apps already exist; inspect before resuming');
    const common={NR_MODE:'synthetic',NR_RADAR_PAUSED:'true',NR_TIMEZONE:'America/Lima',
      NR_DATABASE_URL:dbURL(),NR_SERVICE_TOKEN:secret(),NR_EXTERNAL_CONCURRENCY:'1',
      NR_BATCH_SIZE:'20',NR_WORKER_POLL_SECONDS:'30',NR_WORKER_MAXIMUM_ATTEMPTS:'3',NR_LLM_ENABLED:'false'};
    for(const name of names.slice(1)) {
      const isDashboard=name==='nicheradar-dashboard';
      const env=isDashboard ? {NR_MODE:'synthetic',NR_RADAR_PAUSED:'true',NR_SERVICE_TOKEN:common.NR_SERVICE_TOKEN,
        NR_DASHBOARD_PASSWORD:secret(),NR_API_URL:`http://${project}_nicheradar-api:8000`,NR_DASHBOARD_HOST:'0.0.0.0'} :
        {...common,...(name==='nicheradar-api'?{NR_API_HOST:'0.0.0.0'}:{})};
      cli(['app','create',`${project}/${name}`],{
        env:Object.entries(env).map(([k,v])=>`${k}=${v}`).join('\n'),domains:[],ports:[],mounts:[],
        deploy:{replicas:0,command:name,zeroDowntime:false},resources:resources(isDashboard?0.5:1),
        ...(isDashboard?{basicAuth:[{username:'david',password:secret()}]}:{}),
      });
      // Setting a source does not deploy. Keep zero replicas until migrations succeed.
      cli(['app','update-source-image',`${project}/${name}`,'--yes'],{image:isDashboard?dashboard:backend});
      summarize('app',name);
    }
  } else { throw new Error('Unsupported action'); }
} catch(e) { console.error(e.message); process.exitCode=1; }
