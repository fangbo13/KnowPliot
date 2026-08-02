const navItems = [
  { label: '总览', icon: '◈', active: true },
  { label: '知识空间', icon: '⌘' },
  { label: '知识库', icon: '▤' },
  { label: '参考资料', icon: '◎' },
  { label: '治理中心', icon: '◇' },
];

const metrics = [
  { label: '知识空间', value: '12', change: '+3 本月', tone: 'coral', icon: '⌘' },
  { label: '已沉淀文档', value: '248', change: '+18 本周', tone: 'violet', icon: '▤' },
  { label: '答案覆盖率', value: '92%', change: '+6.4%', tone: 'mint', icon: '✦' },
  { label: '活跃协作流', value: '14', change: '稳定运行', tone: 'amber', icon: '↗' },
];

const coverage = [
  { label: '项目知识', value: '82%', width: '82%', tone: 'coral' },
  { label: '方法论与模板', value: '68%', width: '68%', tone: 'violet' },
  { label: '合规与准则', value: '94%', width: '94%', tone: 'mint' },
  { label: '新人入职', value: '56%', width: '56%', tone: 'amber' },
];

const activities = [
  { title: 'Q2 客户交付复盘', meta: '项目知识 · 18 分钟前', status: '已归档', tone: 'live' },
  { title: 'IFRS 15 收入确认指引', meta: '官方参考库 · 1 小时前', status: '已审核', tone: 'reviewed' },
  { title: '新人入职 30 天路径', meta: '组织知识 · 昨天', status: '待完善', tone: 'pending' },
];

const spaces = [
  { name: '审计交付中台', detail: '42 个知识单元', accent: 'coral' },
  { name: '新人入职导航', detail: '26 个知识单元', accent: 'violet' },
  { name: '合规政策中心', detail: '68 个知识单元', accent: 'mint' },
];

function StaticShowcaseApp() {
  return (
    <div className="showcase-app">
      <aside className="showcase-sidebar" aria-label="KnowPilot 导航">
        <div className="brand-lockup">
          <span className="brand-mark" aria-hidden="true"><span /></span>
          <span className="brand-name">KnowPilot</span>
        </div>
        <p className="brand-kicker">KNOWLEDGE OPERATING SYSTEM</p>

        <nav className="sidebar-nav" aria-label="主导航">
          <p className="nav-label">工作台</p>
          {navItems.map((item) => (
            <div className={`nav-item${item.active ? ' is-active' : ''}`} key={item.label}>
              <span className="nav-icon" aria-hidden="true">{item.icon}</span>
              <span>{item.label}</span>
              {item.active ? <span className="nav-active-dot" aria-hidden="true" /> : null}
            </div>
          ))}
        </nav>

        <div className="sidebar-spaces">
          <div className="sidebar-section-heading">
            <p className="nav-label">最近空间</p>
            <span className="sidebar-count">03</span>
          </div>
          {spaces.map((space) => (
            <div className="space-link" key={space.name}>
              <span className={`space-dot ${space.accent}`} aria-hidden="true" />
              <span className="space-link-copy">
                <strong>{space.name}</strong>
                <small>{space.detail}</small>
              </span>
            </div>
          ))}
        </div>

        <div className="sidebar-footer">
          <div className="health-orbit" aria-hidden="true"><span>92</span></div>
          <div>
            <strong>工作区健康度</strong>
            <small>本周知识覆盖持续提升</small>
          </div>
        </div>
      </aside>

      <main className="showcase-main">
        <header className="showcase-topbar">
          <div className="breadcrumb">
            <span>Workspace</span>
            <span className="breadcrumb-separator" aria-hidden="true">/</span>
            <strong>Executive overview</strong>
          </div>
          <div className="topbar-actions">
            <span className="static-badge"><span className="static-badge-dot" /> 静态演示</span>
            <span className="topbar-divider" aria-hidden="true" />
            <div className="user-avatar" aria-label="当前用户 Haibo Fang">HF</div>
          </div>
        </header>

        <div className="showcase-content">
          <section className="hero-panel">
            <div className="hero-copy">
              <p className="eyebrow"><span className="eyebrow-line" /> KNOWPILOT / 2026</p>
              <h1>让组织的每一个作战单元，都长出自己的大脑。</h1>
              <p className="hero-description">
                把散落在文档、方法论与项目记忆里的知识，整理成可治理、可复用的组织资产。
              </p>
              <div className="hero-meta">
                <span className="hero-meta-icon">✦</span>
                <span>一次提问，多次复用</span>
                <span className="hero-meta-separator" aria-hidden="true" />
                <span>带来源的专业答案</span>
              </div>
            </div>
            <div className="knowledge-orbit" aria-label="知识空间关系示意图">
              <div className="orbit-ring ring-large" />
              <div className="orbit-ring ring-medium" />
              <div className="orbit-ring ring-small" />
              <div className="orbit-center">
                <span className="orbit-center-mark">K</span>
                <span>组织知识</span>
              </div>
              <span className="orbit-node node-top">项目经验</span>
              <span className="orbit-node node-right">方法论</span>
              <span className="orbit-node node-bottom">合规准则</span>
              <span className="orbit-node node-left">团队记忆</span>
              <span className="orbit-star star-one">✦</span>
              <span className="orbit-star star-two">✦</span>
            </div>
          </section>

          <section className="metric-grid" aria-label="工作区概览数据">
            {metrics.map((metric) => (
              <article className="metric-card" key={metric.label}>
                <div className={`metric-icon ${metric.tone}`} aria-hidden="true">{metric.icon}</div>
                <div className="metric-copy">
                  <p>{metric.label}</p>
                  <div className="metric-value-row">
                    <strong>{metric.value}</strong>
                    <span className={`metric-change ${metric.tone}`}>{metric.change}</span>
                  </div>
                </div>
              </article>
            ))}
          </section>

          <section className="insight-grid">
            <article className="content-panel coverage-panel">
              <div className="panel-heading">
                <div>
                  <p className="panel-eyebrow">KNOWLEDGE COVERAGE</p>
                  <h2>知识覆盖地图</h2>
                </div>
                <span className="panel-period">过去 30 天 <span aria-hidden="true">⌄</span></span>
              </div>
              <div className="coverage-list">
                {coverage.map((item) => (
                  <div className="coverage-row" key={item.label}>
                    <div className="coverage-label-row">
                      <span><span className={`coverage-dot ${item.tone}`} aria-hidden="true" />{item.label}</span>
                      <strong>{item.value}</strong>
                    </div>
                    <div className="coverage-track"><span className={`coverage-bar ${item.tone}`} style={{ width: item.width }} /></div>
                  </div>
                ))}
              </div>
              <div className="coverage-footnote"><span className="footnote-check">✓</span> 90% 以上的常见问题已有可引用答案</div>
            </article>

            <article className="feature-panel">
              <div className="feature-glow" aria-hidden="true" />
              <div className="feature-topline">
                <span className="feature-tag">FEATURED SPACE</span>
                <span className="feature-arrow" aria-hidden="true">↗</span>
              </div>
              <div className="feature-content">
                <p className="feature-index">01 / 12</p>
                <h2>审计交付<br /><em>中台</em></h2>
                <p>让每一次判断，都能回到证据与上下文。</p>
                <div className="feature-tags"><span>项目经验</span><span>方法论</span><span>交付模板</span></div>
              </div>
              <div className="feature-bottomline"><span>最近更新 18 分钟前</span><span className="feature-status"><span /> 运转良好</span></div>
            </article>
          </section>

          <section className="lower-grid">
            <article className="content-panel activity-panel">
              <div className="panel-heading">
                <div>
                  <p className="panel-eyebrow">RECENT ACTIVITY</p>
                  <h2>最近知识活动</h2>
                </div>
                <span className="panel-link">查看全部 <span aria-hidden="true">→</span></span>
              </div>
              <div className="activity-list">
                {activities.map((activity) => (
                  <div className="activity-row" key={activity.title}>
                    <div className="activity-icon" aria-hidden="true">↗</div>
                    <div className="activity-copy"><strong>{activity.title}</strong><span>{activity.meta}</span></div>
                    <span className={`activity-status ${activity.tone}`}>{activity.status}</span>
                  </div>
                ))}
              </div>
            </article>

            <article className="content-panel quick-panel">
              <div className="quick-card-mark" aria-hidden="true">✳</div>
              <p className="panel-eyebrow">A QUIET ADVANTAGE</p>
              <h2>知识不是藏起来的资产，<em>而是被持续使用的能力。</em></h2>
              <p className="quick-copy">从一个团队开始，把经验留下来，再让它流向下一个需要的人。</p>
              <div className="quick-footer"><span>KnowPilot principle</span><span>04</span></div>
            </article>
          </section>

          <footer className="showcase-footer">
            <span>KNOWPILOT / KNOWLEDGE OPERATING SYSTEM</span>
            <span>数据为静态展示示例 · 交互与后端服务未接入</span>
          </footer>
        </div>
      </main>
    </div>
  );
}

export default StaticShowcaseApp;
