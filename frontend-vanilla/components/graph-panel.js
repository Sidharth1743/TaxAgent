/**
 * Knowledge Graph — D3.js force-directed graph with circle packing,
 * glow effects, interactive inspector, and animated transitions.
 */

const GraphPanel = (() => {
  let svg = null;
  let simulation = null;
  let container = null;
  let zoomBehavior = null;
  let nodesData = [];
  let linksData = [];
  let width = 0;
  let height = 0;

  // Deep-space neon palette per node type
  const NODE_STYLES = {
    User:         { color: '#6366f1', glow: 'rgba(99,102,241,0.4)',  radius: 16, icon: 'U' },
    Session:      { color: '#14b8a6', glow: 'rgba(20,184,166,0.4)',  radius: 12, icon: 'S' },
    Query:        { color: '#22d3ee', glow: 'rgba(34,211,238,0.4)',  radius: 14, icon: 'Q' },
    Concept:      { color: '#f59e0b', glow: 'rgba(245,158,11,0.4)', radius: 13, icon: 'C' },
    TaxEntity:    { color: '#10b981', glow: 'rgba(16,185,129,0.4)', radius: 13, icon: 'E' },
    Resolution:   { color: '#a855f7', glow: 'rgba(168,85,247,0.4)', radius: 14, icon: 'R' },
    Jurisdiction: { color: '#ec4899', glow: 'rgba(236,72,153,0.4)', radius: 11, icon: 'J' },
    TaxForm:      { color: '#6366f1', glow: 'rgba(99,102,241,0.3)', radius: 11, icon: 'F' },
    Ambiguity:    { color: '#f43f5e', glow: 'rgba(244,63,94,0.4)',  radius: 10, icon: '!' },
  };
  const DEFAULT_STYLE = { color: '#64748b', glow: 'rgba(100,116,139,0.3)', radius: 10, icon: '?' };

  function getStyle(type) { return NODE_STYLES[type] || DEFAULT_STYLE; }

  // ── Init ──────────────────────────────────────────────────

  function init() {
    container = document.getElementById('graphContainer');
    svg = d3.select('#graphSvg');
    if (!container || !svg.node()) return;

    width = container.clientWidth;
    height = container.clientHeight;

    svg.attr('viewBox', [0, 0, width, height]);

    // SVG definitions (glow filters)
    const defs = svg.append('defs');

    // Glow filter
    const filter = defs.append('filter')
      .attr('id', 'glow')
      .attr('x', '-50%').attr('y', '-50%')
      .attr('width', '200%').attr('height', '200%');
    filter.append('feGaussianBlur').attr('stdDeviation', '3').attr('result', 'blur');
    filter.append('feComposite').attr('in', 'SourceGraphic').attr('in2', 'blur').attr('operator', 'over');

    // Stronger glow for hover
    const filterHover = defs.append('filter')
      .attr('id', 'glow-hover')
      .attr('x', '-80%').attr('y', '-80%')
      .attr('width', '260%').attr('height', '260%');
    filterHover.append('feGaussianBlur').attr('stdDeviation', '6').attr('result', 'blur');
    filterHover.append('feComposite').attr('in', 'SourceGraphic').attr('in2', 'blur').attr('operator', 'over');

    // Zoom/pan
    zoomBehavior = d3.zoom()
      .scaleExtent([0.2, 4])
      .on('zoom', (e) => {
        svg.select('.graph-world').attr('transform', e.transform);
      });
    svg.call(zoomBehavior);

    // World group
    svg.append('g').attr('class', 'graph-world');

    // Simulation
    simulation = d3.forceSimulation()
      .force('link', d3.forceLink().id(d => d.id).distance(60).strength(0.3))
      .force('charge', d3.forceManyBody().strength(-120))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius(d => getStyle(d.type).radius + 8))
      .force('x', d3.forceX(width / 2).strength(0.03))
      .force('y', d3.forceY(height / 2).strength(0.03))
      .alphaDecay(0.02)
      .on('tick', ticked);

    simulation.stop();

    // Build legend
    buildLegend();

    // Resize observer
    const ro = new ResizeObserver(() => {
      width = container.clientWidth;
      height = container.clientHeight;
      svg.attr('viewBox', [0, 0, width, height]);
      simulation.force('center', d3.forceCenter(width / 2, height / 2));
      simulation.force('x', d3.forceX(width / 2).strength(0.03));
      simulation.force('y', d3.forceY(height / 2).strength(0.03));
    });
    ro.observe(container);
  }

  function buildLegend() {
    const legendEl = document.getElementById('graphLegend');
    if (!legendEl) return;
    legendEl.innerHTML = '';
    const types = ['User', 'Query', 'Concept', 'TaxEntity', 'Resolution', 'Jurisdiction'];
    types.forEach(t => {
      const s = getStyle(t);
      const item = document.createElement('div');
      item.className = 'graph-legend__item';
      item.innerHTML = `<span class="graph-legend__dot" style="background:${s.color};box-shadow:0 0 4px ${s.glow}"></span>${t}`;
      legendEl.appendChild(item);
    });
  }

  // ── Render ────────────────────────────────────────────────

  function render() {
    if (!svg) return;
    const world = svg.select('.graph-world');

    // Group bubbles — draw translucent circles around nodes of same type
    const groups = d3.group(nodesData, d => d.type);
    world.selectAll('.group-bubble').remove();

    // Links
    const linkSel = world.selectAll('.link-group')
      .data(linksData, d => d.source.id + '-' + d.target.id);

    linkSel.exit().transition().duration(300).attr('opacity', 0).remove();

    const linkEnter = linkSel.enter().append('g').attr('class', 'link-group');
    linkEnter.append('line').attr('class', 'link-line');
    linkEnter.append('text').attr('class', 'link-label');

    const linkAll = linkEnter.merge(linkSel);
    linkAll.select('.link-label').text(d => (d.type || '').replace(/_/g, ' '));

    // Nodes
    const nodeSel = world.selectAll('.node-group')
      .data(nodesData, d => d.id);

    // Exit
    nodeSel.exit().transition().duration(300)
      .attr('opacity', 0)
      .attr('transform', d => `translate(${d.x},${d.y}) scale(0)`)
      .remove();

    // Enter
    const nodeEnter = nodeSel.enter().append('g')
      .attr('class', 'node-group')
      .attr('opacity', 0)
      .call(d3.drag()
        .on('start', dragStart)
        .on('drag', dragging)
        .on('end', dragEnd)
      );

    // Outer glow ring
    nodeEnter.append('circle')
      .attr('class', 'node-glow')
      .attr('r', d => getStyle(d.type).radius + 4)
      .attr('fill', 'none')
      .attr('stroke', d => getStyle(d.type).color)
      .attr('stroke-width', 1)
      .attr('opacity', 0.15);

    // Main circle
    nodeEnter.append('circle')
      .attr('class', 'node-circle')
      .attr('r', d => getStyle(d.type).radius)
      .attr('fill', d => getStyle(d.type).color)
      .attr('fill-opacity', 0.15)
      .attr('stroke', d => getStyle(d.type).color)
      .attr('stroke-width', 1.5)
      .attr('filter', 'url(#glow)');

    // Icon text inside
    nodeEnter.append('text')
      .attr('class', 'node-icon')
      .attr('text-anchor', 'middle')
      .attr('dominant-baseline', 'central')
      .attr('font-family', "'JetBrains Mono', monospace")
      .attr('font-size', d => getStyle(d.type).radius * 0.7)
      .attr('font-weight', 600)
      .attr('fill', d => getStyle(d.type).color)
      .attr('opacity', 0.8)
      .text(d => getStyle(d.type).icon);

    // Label below
    nodeEnter.append('text')
      .attr('class', 'node-label')
      .attr('dy', d => getStyle(d.type).radius + 12)
      .text(d => (d.label || d.id).slice(0, 20));

    // Animate in
    nodeEnter.transition().duration(500)
      .attr('opacity', 1)
      .attrTween('transform', function(d) {
        const ix = d3.interpolate(width/2, d.x || width/2);
        const iy = d3.interpolate(height/2, d.y || height/2);
        const is = d3.interpolate(0, 1);
        return t => `translate(${ix(t)},${iy(t)}) scale(${is(t)})`;
      });

    // Interactions
    nodeEnter
      .on('mouseenter', function(e, d) {
        d3.select(this).select('.node-circle')
          .transition().duration(150)
          .attr('fill-opacity', 0.3)
          .attr('filter', 'url(#glow-hover)')
          .attr('stroke-width', 2);
        d3.select(this).select('.node-glow')
          .transition().duration(150)
          .attr('opacity', 0.4)
          .attr('r', getStyle(d.type).radius + 8);
        showInspector(d);
      })
      .on('mouseleave', function(e, d) {
        d3.select(this).select('.node-circle')
          .transition().duration(300)
          .attr('fill-opacity', 0.15)
          .attr('filter', 'url(#glow)')
          .attr('stroke-width', 1.5);
        d3.select(this).select('.node-glow')
          .transition().duration(300)
          .attr('opacity', 0.15)
          .attr('r', getStyle(d.type).radius + 4);
        hideInspector();
      });

    // Merge
    const nodeAll = nodeEnter.merge(nodeSel);

    // Update simulation
    simulation.nodes(nodesData);
    simulation.force('link').links(linksData);
    simulation.alpha(0.8).restart();
  }

  function ticked() {
    const world = svg.select('.graph-world');

    world.selectAll('.link-group').each(function(d) {
      const g = d3.select(this);
      g.select('.link-line')
        .attr('x1', d.source.x).attr('y1', d.source.y)
        .attr('x2', d.target.x).attr('y2', d.target.y);
      g.select('.link-label')
        .attr('x', (d.source.x + d.target.x) / 2)
        .attr('y', (d.source.y + d.target.y) / 2);
    });

    world.selectAll('.node-group')
      .attr('transform', d => `translate(${d.x},${d.y})`);
  }

  // ── Drag ──────────────────────────────────────────────────

  function dragStart(e, d) {
    if (!e.active) simulation.alphaTarget(0.3).restart();
    d.fx = d.x; d.fy = d.y;
  }
  function dragging(e, d) { d.fx = e.x; d.fy = e.y; }
  function dragEnd(e, d) {
    if (!e.active) simulation.alphaTarget(0);
    d.fx = null; d.fy = null;
  }

  // ── Inspector ─────────────────────────────────────────────

  function showInspector(d) {
    const panel = document.getElementById('nodeInspector');
    if (!panel) return;
    panel.style.display = 'block';
    document.getElementById('inspectorType').textContent = d.type;
    document.getElementById('inspectorType').style.color = getStyle(d.type).color;
    document.getElementById('inspectorLabel').textContent = d.label || d.id;
    document.getElementById('inspectorMeta').textContent = `ID: ${d.id}`;
  }

  function hideInspector() {
    const panel = document.getElementById('nodeInspector');
    if (panel) panel.style.display = 'none';
  }

  // ── Data ──────────────────────────────────────────────────

  async function refresh(userId, sessionId) {
    if (!svg) init();
    if (!svg) return;

    try {
      const params = new URLSearchParams();
      if (userId) params.set('user_id', userId);
      if (sessionId) params.set('session_id', sessionId);

      const resp = await fetch(`/api/graph?${params.toString()}`);
      const data = await resp.json();

      // Merge with existing positions to prevent jumps
      const oldMap = new Map(nodesData.map(n => [n.id, n]));

      nodesData = data.nodes.map(n => {
        const old = oldMap.get(n.id);
        return {
          id: n.id,
          label: n.label || n.id,
          type: n.type,
          x: old ? old.x : width/2 + (Math.random()-0.5)*100,
          y: old ? old.y : height/2 + (Math.random()-0.5)*100,
        };
      });

      // Filter edges to only include links where both source and target exist in nodes
      const nodeIds = new Set(nodesData.map(n => n.id));
      linksData = data.edges
        .filter(e => nodeIds.has(e.from) && nodeIds.has(e.to))
        .map(e => ({
          source: e.from,
          target: e.to,
          type: e.type || '',
        }));

      render();
    } catch (err) {
      console.warn('Graph refresh failed:', err);
    }
  }

  /** Dynamically add a node (called after memory persist). */
  function addNode(id, label, type) {
    if (nodesData.find(n => n.id === id)) return;
    nodesData.push({
      id, label: label || id, type,
      x: width/2 + (Math.random()-0.5)*60,
      y: height/2 + (Math.random()-0.5)*60,
    });
    render();
  }

  return { init, refresh, addNode };
})();
