/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import React from "react";
import {
  AbsoluteFill,
  Audio,
  Easing,
  interpolate,
  Sequence,
  staticFile,
  useCurrentFrame,
} from "remotion";

const FPS = 30;
const frameOf = (seconds: number) => Math.round(seconds * FPS);

const timeline = {
  opening: [0, 20],
  brand: [20, 35],
  chat: [35, 75],
  knowledge: [75, 115],
  crawler: [115, 145],
  rbac: [145, 175],
  feedback: [175, 195],
  scenarios: [195, 212],
  finale: [212, 225],
} as const;

type SceneKey = keyof typeof timeline;
type SceneProps = { duration: number };

const clamp = {
  extrapolateLeft: "clamp" as const,
  extrapolateRight: "clamp" as const,
};

const ease = Easing.bezier(0.16, 1, 0.3, 1);
const soft = Easing.bezier(0.45, 0, 0.55, 1);

const reveal = (frame: number, start: number, duration = 20) =>
  interpolate(frame, [start, start + duration], [0, 1], {
    ...clamp,
    easing: ease,
  });

const progress = (frame: number, duration: number) =>
  interpolate(frame, [0, duration], [0, 1], clamp);

const fadeScene = (frame: number, duration: number) => {
  const fadeIn = interpolate(frame, [0, 18], [0, 1], {
    ...clamp,
    easing: Easing.out(Easing.cubic),
  });
  const fadeOut = interpolate(frame, [duration - 18, duration], [1, 0], {
    ...clamp,
    easing: Easing.in(Easing.cubic),
  });
  return Math.min(fadeIn, fadeOut);
};

const sceneDuration = (key: SceneKey) => frameOf(timeline[key][1] - timeline[key][0]);
const sceneStart = (key: SceneKey) => frameOf(timeline[key][0]);
const cn = (...items: Array<string | false | undefined>) => items.filter(Boolean).join(" ");

export const KnowPilotDemo: React.FC = () => (
  <AbsoluteFill className="kp-root">
    <AudioLayer />
    {(Object.keys(timeline) as SceneKey[]).map((key) => (
      <Sequence key={key} from={sceneStart(key)} durationInFrames={sceneDuration(key)}>
        <SceneSwitch sceneKey={key} duration={sceneDuration(key)} />
      </Sequence>
    ))}
  </AbsoluteFill>
);

const SceneSwitch: React.FC<{ sceneKey: SceneKey; duration: number }> = ({
  sceneKey,
  duration,
}) => {
  switch (sceneKey) {
    case "opening":
      return <OpeningScene duration={duration} />;
    case "brand":
      return <BrandScene duration={duration} />;
    case "chat":
      return <ChatScene duration={duration} />;
    case "knowledge":
      return <KnowledgeScene duration={duration} />;
    case "crawler":
      return <CrawlerScene duration={duration} />;
    case "rbac":
      return <RbacScene duration={duration} />;
    case "feedback":
      return <FeedbackScene duration={duration} />;
    case "scenarios":
      return <ScenarioScene duration={duration} />;
    case "finale":
      return <FinaleScene duration={duration} />;
  }
};

const AudioLayer: React.FC = () => (
  <>
    <Audio
      src={staticFile("audio/background-score.mp3")}
      volume={(frame) => {
        const seconds = frame / FPS;
        if (seconds < 30) return 0.18;
        if (seconds < 175) return 0.2;
        if (seconds < 210) return 0.23;
        return interpolate(seconds, [210, 225], [0.18, 0], clamp);
      }}
    />
    <Voiceover />
    <Sfx />
  </>
);

const Voiceover: React.FC = () => {
  const clips: Array<[number, string]> = [
    [1.8, "voiceover/s01-opening.wav"],
    [21.5, "voiceover/s02-brand.wav"],
    [38, "voiceover/s03-chat.wav"],
    [78, "voiceover/s04-knowledge.wav"],
    [118, "voiceover/s05-crawler.wav"],
    [148, "voiceover/s06-rbac.wav"],
    [177.5, "voiceover/s07-feedback.wav"],
    [196.2, "voiceover/s08-scenarios.wav"],
    [216.5, "voiceover/s09-finale.wav"],
  ];
  return (
    <>
      {clips.map(([from, file]) => (
        <Sequence key={file} from={frameOf(from)} layout="none">
          <Audio src={staticFile(`audio/${file}`)} volume={0.9} />
        </Sequence>
      ))}
    </>
  );
};

const Sfx: React.FC = () => {
  const cues: Array<[number, string, number]> = [
    [20.2, "sfx/soft-whoosh.wav", 0.11],
    [31.4, "sfx/light-chime.wav", 0.08],
    [40.2, "sfx/soft-click.wav", 0.07],
    [44.7, "sfx/key.wav", 0.06],
    [49.2, "sfx/soft-click.wav", 0.07],
    [53.6, "sfx/ui-tick.wav", 0.055],
    [63.8, "sfx/soft-click.wav", 0.07],
    [76.2, "sfx/soft-whoosh.wav", 0.08],
    [82.8, "sfx/soft-click.wav", 0.07],
    [89.6, "sfx/light-chime.wav", 0.09],
    [101.2, "sfx/ui-tick.wav", 0.055],
    [115.3, "sfx/soft-whoosh.wav", 0.08],
    [121.8, "sfx/key.wav", 0.055],
    [126.4, "sfx/soft-click.wav", 0.07],
    [137.5, "sfx/ui-tick.wav", 0.055],
    [145.4, "sfx/soft-whoosh.wav", 0.08],
    [157.3, "sfx/ui-tick.wav", 0.055],
    [167.1, "sfx/ui-tick.wav", 0.055],
    [175.2, "sfx/soft-whoosh.wav", 0.08],
    [185.2, "sfx/light-chime.wav", 0.075],
    [212.2, "sfx/soft-whoosh.wav", 0.08],
  ];
  return (
    <>
      {cues.map(([from, file, volume], index) => (
        <Sequence key={`${file}-${index}`} from={frameOf(from)} layout="none">
          <Audio src={staticFile(`audio/${file}`)} volume={volume} />
        </Sequence>
      ))}
    </>
  );
};

const BaseScene: React.FC<{
  children: React.ReactNode;
  duration: number;
  variant?: "default" | "blue";
}> = ({ children, duration, variant = "default" }) => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill
      className={cn("scene", variant === "blue" && "scene-blue")}
      style={{ opacity: fadeScene(frame, duration) }}
    >
      <div className="background-grid" />
      {children}
    </AbsoluteFill>
  );
};

const Subtitle: React.FC<{ children: React.ReactNode; top?: number }> = ({
  children,
  top = 902,
}) => (
  <div className="subtitle" style={{ top }}>
    {children}
  </div>
);

const Callout: React.FC<{ x: number; y: number; show: number; children: React.ReactNode }> = ({
  x,
  y,
  show,
  children,
}) => (
  <div
    className="callout"
    style={{
      left: x,
      top: y,
      opacity: show,
      transform: `translateY(${interpolate(show, [0, 1], [8, 0])}px)`,
    }}
  >
    {children}
  </div>
);

const Spotlight: React.FC<{ x: number; y: number; w: number; h: number; show: number }> = ({
  x,
  y,
  w,
  h,
  show,
}) => <div className="spotlight" style={{ left: x, top: y, width: w, height: h, opacity: show }} />;

const Cursor: React.FC<{ start?: number; points: Array<[number, number, number]> }> = ({
  start = 0,
  points,
}) => {
  const frame = useCurrentFrame();
  const t = Math.max(0, frame - start);
  let x = points[0][0];
  let y = points[0][1];
  for (let i = 0; i < points.length - 1; i += 1) {
    const [x1, y1, t1] = points[i];
    const [x2, y2, t2] = points[i + 1];
    if (t >= t1 && t <= t2) {
      const p = interpolate(t, [t1, t2], [0, 1], { ...clamp, easing: soft });
      x = interpolate(p, [0, 1], [x1, x2]);
      y = interpolate(p, [0, 1], [y1, y2]);
      break;
    }
    if (t > t2) {
      x = x2;
      y = y2;
    }
  }
  return <div className="cursor" style={{ transform: `translate(${x}px, ${y}px)` }} />;
};

const OpeningScene: React.FC<SceneProps> = ({ duration }) => {
  const frame = useCurrentFrame();
  const p = progress(frame, duration);
  const docs = [
    ["PDF", "IFRS 15", 240, 170, -5],
    ["XLSX", "Archive Checklist", 1030, 185, 3],
    ["MD", "Client Meeting Notes", 468, 455, 2],
    ["DOCX", "Audit Methodology", 795, 120, -2],
    ["LOG", "Project Records", 1115, 468, -3],
  ];
  return (
    <BaseScene duration={duration}>
      <div
        className="opening-stage"
        style={{
          transform: `scale(${interpolate(p, [0, 1], [0.96, 1.03], clamp)}) translateY(${interpolate(p, [0, 1], [12, -6], clamp)}px)`,
        }}
      >
        {docs.map(([type, title, x, y, rotate], index) => (
          <DocCard
            key={String(title)}
            type={String(type)}
            title={String(title)}
            x={Number(x)}
            y={Number(y)}
            rotate={Number(rotate)}
            show={reveal(frame, 8 + index * 12, 20)}
          />
        ))}
        <div className="floating-search" style={{ opacity: reveal(frame, 140, 22) }}>
          这个调整为什么这么做？
        </div>
      </div>
      <div className="opening-tags">
        {["知识散落。", "答案不一致。", "经验难传承。"].map((item, index) => (
          <span key={item} style={{ opacity: reveal(frame, 265 + index * 24, 16) }}>
            {item}
          </span>
        ))}
      </div>
      <Subtitle>
        专业服务团队每天都在寻找知识。流程、准则、底稿、项目判断，常常散落在不同文件和人的记忆里。
      </Subtitle>
    </BaseScene>
  );
};

const BrandScene: React.FC<SceneProps> = ({ duration }) => {
  const frame = useCurrentFrame();
  const p = progress(frame, duration);
  const cards = ["PDF", "DOCX", "XLSX", "WEB", "NOTES"];
  return (
    <BaseScene duration={duration} variant="blue">
      <div className="brand-stage">
        {cards.map((item, index) => {
          const angle = (index / cards.length) * Math.PI * 2;
          const distance = interpolate(p, [0, 0.76], [390, 72], {
            ...clamp,
            easing: soft,
          });
          return (
            <div
              key={item}
              className="mini-card"
              style={{
                opacity: interpolate(p, [0, 0.18, 0.82, 1], [0, 1, 1, 0.18], clamp),
                transform: `translate(${Math.cos(angle) * distance}px, ${Math.sin(angle) * distance * 0.62}px)`,
              }}
            >
              {item}
            </div>
          );
        })}
        <div className="knowledge-core">KP</div>
        <div className="brand-lockup" style={{ opacity: reveal(frame, 180, 24) }}>
          <h1>KnowPilot — 知识领航</h1>
          <p>RAG 驱动的知识库应用 Agent</p>
        </div>
      </div>
      <Subtitle>从入职问答，升级为组织级知识库 Agent。</Subtitle>
    </BaseScene>
  );
};

const ChatScene: React.FC<SceneProps> = ({ duration }) => {
  const frame = useCurrentFrame();
  const p = progress(frame, duration);
  const question = "CAS 与 HKFRS 对租赁确认的差异是什么？";
  const answer =
    "可以从三个方面复核：\n\n1. 租赁识别：两套准则都强调控制使用权，但披露口径存在差异。\n2. 初始计量：折现率选择需要结合本地实践和合同付款安排。\n3. 后续披露：HKFRS 对关键判断和敏感性披露要求更细。\n\n建议在底稿中引用准则条款，并补充客户合同中的关键判断。";
  const questionCount = Math.floor(interpolate(frame, [150, 255], [0, question.length], clamp));
  const answerCount = Math.floor(interpolate(frame, [455, 900], [0, answer.length], clamp));
  const status = frame < 350 ? "connecting" : frame < 455 ? "searching" : frame < 900 ? "generating" : "complete";
  const citations = reveal(frame, 845, 28);
  return (
    <BaseScene duration={duration}>
      <div
        className="app-camera"
        style={{
          transform: `scale(${interpolate(p, [0, 1], [0.9, 1.02], { ...clamp, easing: soft })}) translateY(${interpolate(p, [0, 1], [8, -5], clamp)}px)`,
        }}
      >
        <AppShell active="Chat" role="Employee">
          <div className="chat-grid">
            <aside className="sessions">
              <button className="new-chat">New Chat</button>
              {["租赁准则差异", "IPO 历史判断", "报销流程"].map((item, index) => (
                <div key={item} className={cn("session", index === 0 && "active")}>
                  {item}
                  <span>{index === 0 ? "Now" : "Recent"}</span>
                </div>
              ))}
            </aside>
            <section className="chat-area">
              <div className="message user">{question.slice(0, questionCount)}{questionCount < question.length ? "|" : ""}</div>
              <div className="status-row">
                {["connecting", "searching", "generating"].map((item) => (
                  <span key={item} className={cn(status === item && "live", status === "complete" && "done")}>
                    {item}
                  </span>
                ))}
              </div>
              <div className="answer-card">
                <pre>{answer.slice(0, answerCount)}{answerCount < answer.length ? "▌" : ""}</pre>
              </div>
              <div className="source-toggle" style={{ opacity: citations }}>
                <span>›</span>
                <span>⛓</span>
                <b>8 个来源</b>
              </div>
              <div className="composer">
                <span>在此输入你的问题...</span>
                <button>▷</button>
              </div>
            </section>
          </div>
        </AppShell>
        <Spotlight x={670} y={640} w={170} h={42} show={citations} />
        <Cursor start={96} points={[[328, 172, 0], [438, 655, 68], [560, 655, 138], [744, 662, 790]]} />
      </div>
      <Callout x={500} y={142} show={reveal(frame, 360, 20)}>先检索，再生成</Callout>
      <Callout x={1030} y={620} show={citations}>来源在回答下方</Callout>
      <Subtitle>
        用户只需要提出问题。KnowPilot 会先检索知识库，再生成结构化答案。回答完成后，来源会自动附在下方，方便复核和追溯。
      </Subtitle>
    </BaseScene>
  );
};

const KnowledgeScene: React.FC<SceneProps> = ({ duration }) => {
  const frame = useCurrentFrame();
  const p = progress(frame, duration);
  const status = frame < 270 ? "草稿" : frame < 520 ? "处理中" : frame < 790 ? "已激活" : frame < 925 ? "处理中" : "已激活";
  const chunks = frame < 500 ? "0" : "128";
  return (
    <BaseScene duration={duration}>
      <div className="app-camera" style={{ transform: `scale(${interpolate(p, [0, 1], [0.92, 1.02], { ...clamp, easing: soft })})` }}>
        <AppShell active="Knowledge Base" role="Content Admin">
          <div className="page-header">
            <div>
              <h2>Knowledge Base Admin</h2>
              <p>Upload, validate, chunk and index team knowledge.</p>
            </div>
            <button className="primary">Upload</button>
          </div>
          <div className="validation" style={{ opacity: reveal(frame, 150, 18) }}>
            支持 PDF、DOCX、TXT、CSV、XLSX、PPTX
          </div>
          <DocTable status={status} chunks={chunks} />
        </AppShell>
        <Spotlight x={1192} y={118} w={108} h={46} show={reveal(frame, 105, 20)} />
        <Spotlight x={655} y={352} w={420} h={76} show={reveal(frame, 345, 20)} />
        <Spotlight x={1015} y={352} w={245} h={76} show={reveal(frame, 760, 20)} />
        <Cursor start={85} points={[[1248, 140, 0], [1248, 140, 54], [1125, 390, 745], [1180, 390, 835]]} />
      </div>
      <Callout x={348} y={160} show={reveal(frame, 160, 18)}>上传后自动切块</Callout>
      <Callout x={770} y={440} show={reveal(frame, 400, 18)}>处理状态实时反馈</Callout>
      <Callout x={1068} y={440} show={reveal(frame, 800, 18)}>一键重新索引</Callout>
      <Subtitle>
        管理员上传文档后，系统会完成校验、切块和索引。处理状态清楚显示在表格中。知识更新后，可以一键重新索引，保证问答使用最新内容。
      </Subtitle>
    </BaseScene>
  );
};

const CrawlerScene: React.FC<SceneProps> = ({ duration }) => {
  const frame = useCurrentFrame();
  const p = progress(frame, duration);
  const steps = ["Fetch", "Parse", "Clean", "Embed", "Active"];
  const active = Math.min(steps.length - 1, Math.floor(interpolate(frame, [210, 610], [0, steps.length - 0.01], clamp)));
  const withdrawn = frame > 735;
  return (
    <BaseScene duration={duration}>
      <div className="app-camera" style={{ transform: `scale(${interpolate(p, [0, 1], [0.94, 1.02], { ...clamp, easing: soft })})` }}>
        <AppShell active="Web Crawler" role="System Admin">
          <div className="page-header">
            <div>
              <h2>Web Crawler</h2>
              <p>Collect authorized web knowledge with governance controls.</p>
            </div>
          </div>
          <div className="crawler-form">
            <div className="url-input">https://knowledge.example.com/audit/lease-standard</div>
            <div className="toggle"><i /> Internal Only</div>
            <button className="primary">Submit</button>
          </div>
          <div className="stepper">
            {steps.map((step, index) => (
              <div key={step} className={cn(index <= active && "done", index === active && "current")}>
                {step}
              </div>
            ))}
          </div>
          <div className="crawl-result">
            <b>knowledge.example.com/audit/lease-standard</b>
            <span>{withdrawn ? "withdrawn" : steps[active].toLowerCase()} · internal only · {withdrawn ? "0" : "64"} chunks</span>
            <button>{withdrawn ? "Withdrawn" : "Withdraw"}</button>
          </div>
        </AppShell>
        <Cursor start={82} points={[[455, 250, 0], [895, 250, 80], [1030, 250, 150], [1170, 250, 190], [1130, 504, 640]]} />
      </div>
      <Callout x={360} y={197} show={reveal(frame, 90, 18)}>网页知识自动采集</Callout>
      <Callout x={930} y={197} show={reveal(frame, 165, 18)}>Internal Only</Callout>
      <Callout x={1030} y={535} show={reveal(frame, 650, 18)}>内容可撤回</Callout>
      <Subtitle>
        网页内容也可以采集入库。Internal Only 用来标记内部或授权内容。如果内容过期或授权变化，可以撤回出检索范围。
      </Subtitle>
    </BaseScene>
  );
};

const RbacScene: React.FC<SceneProps> = ({ duration }) => {
  const frame = useCurrentFrame();
  const p = progress(frame, duration);
  const userFocus = reveal(frame, 80, 18);
  const healthFocus = reveal(frame, 330, 18);
  const rbacFocus = reveal(frame, 575, 18);
  return (
    <BaseScene duration={duration}>
      <div
        className="app-camera"
        style={{
          transform: `scale(${interpolate(p, [0, 1], [0.94, 1.01], { ...clamp, easing: soft })}) translateY(${interpolate(p, [0, 1], [6, -3], clamp)}px)`,
        }}
      >
        <AppShell active="Admin Dashboard" role="System Admin">
          <div className="admin-dashboard">
            <section className="admin-panel users-panel">
              <div className="panel-title">
                <b>admin_users</b>
                <button>Refresh</button>
              </div>
              <UserAdminTable />
            </section>
            <section className="admin-panel health-panel">
              <div className="panel-title">
                <b>System Health</b>
              </div>
              <div className="health-table">
                {[
                  ["Backend", "running"],
                  ["Celery", "running"],
                  ["Database", "connected"],
                  ["Total Users", "3"],
                  ["Active Users", "3"],
                ].map(([label, value]) => (
                  <div key={label}>
                    <span>{label}</span>
                    <b>{value}</b>
                  </div>
                ))}
              </div>
              <div className="rbac-banner">
                <b>V4.0 Dual-Track RBAC Active</b>
                <span>HR: Content domain (22 perms) · Admin: System domain (35 perms)</span>
              </div>
            </section>
          </div>
        </AppShell>
        <Spotlight x={570} y={205} w={470} h={170} show={userFocus} />
        <Spotlight x={1395} y={220} w={300} h={155} show={healthFocus} />
        <Spotlight x={1400} y={438} w={420} h={78} show={rbacFocus} />
        <Cursor start={70} points={[[1260, 138, 0], [1260, 138, 80], [1560, 242, 320], [1590, 458, 575]]} />
      </div>
      <Callout x={525} y={545} show={userFocus}>角色与账号清晰可见</Callout>
      <Callout x={1145} y={545} show={healthFocus}>系统状态实时反馈</Callout>
      <Callout x={1380} y={650} show={rbacFocus}>权限域分离</Callout>
      <Subtitle>
        普通用户访问问答入口。内容管理员维护知识资产。系统管理员管理用户、采集、系统状态和权限边界。不同角色，只看到自己该看到的功能。
      </Subtitle>
    </BaseScene>
  );
};

const FeedbackScene: React.FC<SceneProps> = ({ duration }) => {
  const frame = useCurrentFrame();
  const cards = [
    ["上传成功", "Revenue_Guide.pdf indexed successfully", "success"],
    ["文件类型错误", "Only PDF, DOCX, TXT, CSV, XLSX and PPTX are supported", "error"],
    ["网络离线", "Draft saved locally. Reconnect to send.", "warning"],
    ["发送按钮 disabled", "Enter a question to continue", "muted"],
    ["Stop generation", "Response streaming can be stopped", "blue"],
    ["Retry Alert", "Request failed. Retry is available.", "warning"],
  ];
  return (
    <BaseScene duration={duration}>
      <div className="feedback-stage">
        <div className="feedback-grid">
          {cards.map(([title, copy, tone], index) => (
            <div key={title} className={cn("feedback-card", tone)} style={{ opacity: reveal(frame, 18 + index * 22, 14) }}>
              <b>{title}</b>
              <span>{copy}</span>
            </div>
          ))}
        </div>
        <div className="audit-log">
          <h3>Audit Log</h3>
          {["09:31 upload_document", "09:34 reindex_document", "09:40 withdraw_crawl", "09:45 user_login"].map((item, index) => (
            <div key={item} style={{ opacity: reveal(frame, 335 + index * 22, 14) }}>
              <i />
              <span>{item}</span>
            </div>
          ))}
        </div>
      </div>
      <Callout x={320} y={150} show={reveal(frame, 70, 18)}>即时反馈</Callout>
      <Callout x={735} y={150} show={reveal(frame, 135, 18)}>错误可恢复</Callout>
      <Callout x={1138} y={240} show={reveal(frame, 338, 18)}>关键操作自动留痕</Callout>
      <Subtitle>
        KnowPilot 在上传、生成、离线和错误时都给出明确反馈。关键操作进入审计日志，做到可恢复，也可追踪。
      </Subtitle>
    </BaseScene>
  );
};

const ScenarioScene: React.FC<SceneProps> = ({ duration }) => {
  const frame = useCurrentFrame();
  const index = frame < frameOf(5.7) ? 0 : frame < frameOf(11.4) ? 1 : 2;
  const data = [
    ["入职培训", "报销发票怎么分类？", "按费用用途选择差旅、办公或客户项目，并补充项目编码。", "Reimbursement_Guide.pdf"],
    ["项目经验沉淀", "这个 IPO 项目去年拒函的原因是什么？", "主要原因是收入确认证据不足和关联方披露不完整。", "Client_Meeting_Notes.md"],
    ["准则问答", "IFRS 15 收入确认五步法怎么适用？", "先识别合同和履约义务，再判断交易价格与收入确认时点。", "IFRS15_Revenue.pdf"],
  ];
  const [label, question, answer, source] = data[index];
  return (
    <BaseScene duration={duration}>
      <div className="scenario-card">
        <div className="scenario-label">{label}</div>
        <div className="scenario-question">{question}</div>
        <div className="scenario-answer">{answer}</div>
        <div className="scenario-source">来源：{source}</div>
      </div>
      <Subtitle>同一套引擎，可以服务不同场景。新人查流程，项目组追溯判断，审计团队查询准则依据。</Subtitle>
    </BaseScene>
  );
};

const FinaleScene: React.FC<SceneProps> = ({ duration }) => {
  const frame = useCurrentFrame();
  const teamFade = reveal(frame, 5, 18);
  const logoFade = reveal(frame, 165, 24);
  const teams = ["审计一部", "审计二部", "人才团队", "咨询团队"];
  return (
    <BaseScene duration={duration} variant="blue">
      <div className="final-teams" style={{ opacity: interpolate(logoFade, [0, 1], [teamFade, 0.2], clamp) }}>
        <div className="engine">KnowPilot Engine</div>
        {teams.map((team, index) => (
          <div key={team} className="team-card" style={{ opacity: reveal(frame, 26 + index * 13, 14) }}>
            <b>{team}</b>
            <span>{["准则问答", "IPO 案例库", "入职宝典", "行业方法论"][index]}</span>
          </div>
        ))}
      </div>
      <div className="final-logo" style={{ opacity: logoFade }}>
        <div className="logo-mark">KP</div>
        <h1>KnowPilot — 知识领航</h1>
        <h2>RAG 驱动的知识库应用 Agent</h2>
        <p>让组织的每一个作战单元，都长出自己的大脑。</p>
      </div>
      <Subtitle top={918}>KnowPilot，让组织知识可用、可管、可追溯。</Subtitle>
    </BaseScene>
  );
};

const DocCard: React.FC<{ type: string; title: string; x: number; y: number; rotate: number; show: number }> = ({
  type,
  title,
  x,
  y,
  rotate,
  show,
}) => (
  <div
    className="doc-card"
    style={{
      left: x,
      top: y,
      opacity: show,
      transform: `rotate(${rotate}deg) translateY(${interpolate(show, [0, 1], [18, 0])}px)`,
    }}
  >
    <span>{type}</span>
    <b>{title}</b>
    <i /><i /><i />
  </div>
);

const AppShell: React.FC<{ active: string; role: string; children: React.ReactNode }> = ({
  active,
  role,
  children,
}) => {
  return (
    <div className={cn("app-shell real-shell", active === "Chat" && "chat-shell")}>
      <aside className="real-sidebar">
        <div className="real-brand">
          <div className="app-logo">KP</div>
          <b>KnowPilot</b>
          <span>⌕</span>
          <span>▦</span>
        </div>
        <button className="sidebar-new">＋ 开启新对话</button>
        <div className="sidebar-search">⌕ 搜索对话</div>
        <div className="sidebar-group">› 更早 <i>{active === "Chat" ? "41" : "40"}</i></div>
        <div className="sidebar-spacer" />
        <div className="sidebar-user">
          <span>◯</span>
          <b>admin@test.knowpilot.com</b>
          <i>↻</i>
        </div>
      </aside>
      <section className="real-main">
        <header className="real-topbar">
          <div />
          <nav>
            <span>🌐</span>
            <span>☾</span>
            <span className="avatar">◯</span>
            <b>admin@test.knowpilot.com</b>
          </nav>
        </header>
        <main className="app-main">
          <div className="role-badge">{role}</div>
          {children}
        </main>
      </section>
    </div>
  );
};

const DocTable: React.FC<{ status: string; chunks: string }> = ({ status, chunks }) => {
  const rows = [
    ["CAS_HKFRS_Lease_Difference.pdf", "Accounting", "pdf", chunks, status, "2026-06-28 18:14:05", "重建索引  删除"],
    ["KnowPilot 办公室信息与入职指南", "Office Info", "txt", "5", "处理中", "2026-06-18 02:48:57", "重建索引  删除"],
    ["Training and Career Development Guide", "Training", "txt", "17", "处理中", "2026-06-18 02:48:56", "重建索引  删除"],
    ["新员工入职 Checklist", "HR Policies", "txt", "3", "处理中", "2026-06-18 02:48:56", "重建索引  删除"],
    ["Compliance and Code of Conduct", "Compliance", "txt", "13", "已激活", "2026-06-18 02:48:55", "重建索引  删除"],
    ["HR 政策与员工福利手册", "HR Policies", "txt", "4", "已激活", "2026-06-18 02:48:55", "重建索引  删除"],
  ];
  return <Table columns={["标题", "分类", "类型", "分块数", "状态", "创建时间", "操作"]} rows={rows} />;
};

const Table: React.FC<{ columns: string[]; rows: string[][] }> = ({ columns, rows }) => (
  <table className="data-table">
    <thead>
      <tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr>
    </thead>
    <tbody>
      {rows.map((row, rowIndex) => (
        <tr key={rowIndex}>
          {row.map((cell, cellIndex) => (
            <td key={`${cell}-${cellIndex}`}>
              {cellIndex === 4 ? <span className={cn("status-pill", statusClass(cell))}>{cell}</span> : cell}
            </td>
          ))}
        </tr>
      ))}
    </tbody>
  </table>
);

const statusClass = (value: string) => {
  if (value === "已激活" || value === "active") return "active";
  if (value === "处理中" || value === "processing") return "processing";
  return "draft";
};

const UserAdminTable: React.FC = () => {
  const rows = [
    ["admin@test.knowpilot.com", "admin", "ADMIN · HR", "-", "Active"],
    ["employee@test.knowpilot.com", "employee", "Employee", "-", "Active"],
    ["hr@test.knowpilot.com", "hr_user", "HR", "-", "Active"],
  ];
  return (
    <table className="admin-users-table">
      <thead>
        <tr>
          {["Email", "Username", "Role", "Service Line", "Active"].map((column) => (
            <th key={column}>{column}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row[0]}>
            {row.map((cell, index) => (
              <td key={cell}>
                {index === 2 ? (
                  <span className="role-tags">{cell}</span>
                ) : index === 4 ? (
                  <span className="status-pill active">{cell}</span>
                ) : (
                  cell
                )}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
};
