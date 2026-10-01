/* 보안정보 브리핑 — data/manifest.json을 읽어 포털·목록 페이지를 채운다.
   - 외부 요청 없음. 경로는 전부 상대경로(저장소 이전·하위 경로 배포에도 그대로 동작)
   - 화면에 넣는 값은 textContent로만 다룬다(innerHTML 미사용)
   - <html data-root="" data-page="portal|kisa-cert|law"> 로 페이지를 구분 */
(function () {
  "use strict";

  var LABELS = { "daily": "데일리", "kisa-cert": "KISA 주간", "law": "법령·제도 분석" };
  var DOW = ["일", "월", "화", "수", "목", "금", "토"];
  var root = document.documentElement;
  var ROOT = root.getAttribute("data-root") || "";
  var PAGE = root.getAttribute("data-page") || "portal";

  function byId(id) { return document.getElementById(id); }

  function append(node, children) {
    [].concat(children == null ? [] : children).forEach(function (c) {
      node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    });
    return node;
  }

  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) { node.setAttribute(k, attrs[k]); });
    return append(node, children);
  }

  function fill(id, children) {
    var node = byId(id);
    if (!node) return;
    node.textContent = "";
    append(node, children);
  }

  function ymd(d) {
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(d || "");
    return m ? [+m[1], +m[2], +m[3]] : null;
  }
  function two(n) { return (n < 10 ? "0" : "") + n; }
  function dow(p) { return DOW[new Date(Date.UTC(p[0], p[1] - 1, p[2])).getUTCDay()]; }
  // 공문서 날짜 표기: 2026. 10. 1.(목)
  function longDate(d) { var p = ymd(d); return p ? p[0] + ". " + p[1] + ". " + p[2] + ".(" + dow(p) + ")" : "날짜 미상"; }
  function monthDay(d) { var p = ymd(d); return p ? p[1] + ". " + p[2] + ".(" + dow(p) + ")" : ""; }
  function shortDate(d) { var p = ymd(d); return p ? two(p[1]) + "." + two(p[2]) : "-"; }
  function todayKST() { return new Date(Date.now() + 9 * 3600 * 1000).toISOString().slice(0, 10); }
  function href(item) { return ROOT + item.url; }
  function only(items, cat) { return items.filter(function (i) { return i.cat === cat; }); }

  function newestFirst(a, b) {
    if (a.date !== b.date) return a.date < b.date ? 1 : -1;
    return a.url < b.url ? 1 : -1;
  }

  function row(item, withCat) {
    var cells = [el("td", { "class": "d" }, el("time", { datetime: item.date, title: longDate(item.date) }, shortDate(item.date)))];
    if (withCat) {
      cells.push(el("td", { "class": "c" }, el("span", { "class": "tag", "data-cat": item.cat }, LABELS[item.cat] || item.cat)));
    }
    var title = [el("a", { href: href(item) }, item.title)];
    if (!withCat && item.desc) title.push(el("span", { "class": "sub" }, item.desc));
    cells.push(el("td", { "class": "t" }, title));
    return el("tr", null, cells);
  }

  function renderPortal(items) {
    var d = only(items, "daily")[0];
    var link = byId("lead-link");
    if (d) {
      var fresh = d.date === todayKST();
      fill("lead-date", [
        el("span", { "class": "big" }, longDate(d.date)),
        el("span", { "class": fresh ? "state now" : "state" }, fresh ? "오늘" : "최신")
      ]);
      fill("lead-count", d.total != null ? d.total + "건" + (d.major != null ? " (주요 " + d.major + "건)" : "") : "-");
      fill("lead-headline", d.headline || d.desc || "-");
      link.href = href(d);
      link.textContent = fresh ? "오늘의 보안이슈 보기" : longDate(d.date) + " 호 보기";
    } else {
      fill("lead-date", "아직 발행된 호가 없습니다.");
    }

    ["daily", "kisa-cert", "law"].forEach(function (cat) {
      var slot = document.querySelector('[data-latest="' + cat + '"]');
      if (!slot) return;
      var list = only(items, cat);
      slot.textContent = "";
      if (!list.length) { slot.textContent = "아직 발행된 자료가 없습니다."; return; }
      var it = list[0];
      append(slot, [
        "최근 ",
        el("a", { href: href(it) }, cat === "daily" ? longDate(it.date) + " 호" : it.title),
        el("span", { "class": "count" }, "전체 " + list.length + "건")
      ]);
    });

    // 데일리는 위에서 따로 보여 주므로 여기서는 분석 자료(KISA 주간·법령)만
    var body = byId("ledger-body");
    var rows = items.filter(function (i) { return i.cat !== "daily"; }).slice(0, 8);
    body.textContent = "";
    if (!rows.length) {
      body.appendChild(el("tr", null, el("td", { colspan: "3", "class": "empty" }, "아직 게시된 분석 자료가 없습니다.")));
    }
    rows.forEach(function (it) { body.appendChild(row(it, true)); });
  }

  function renderSeries(items) {
    var it = items[0];
    var link = byId("lead-link");
    if (it) {
      var lead = [el("span", { "class": "big" }, longDate(it.date))];
      var s = ymd(it.date), u = ymd(it.until);
      if (s && u) lead.push(" ", el("span", { "class": "range" }, "~ " + (u[0] !== s[0] ? longDate(it.until) : monthDay(it.until))));
      fill("lead-date", lead);
      fill("lead-title", it.title);
      link.href = href(it);
    } else {
      fill("lead-date", "아직 게시된 자료가 없습니다.");
      fill("lead-title", "-");
      link.hidden = true;
    }

    var table = byId("archive");
    Array.prototype.slice.call(table.tBodies).forEach(function (tb) { table.removeChild(tb); });
    if (!items.length) {
      table.appendChild(el("tbody", null, el("tr", null, el("td", { colspan: "2", "class": "empty" }, "아직 게시된 자료가 없습니다."))));
      return;
    }
    var group = null;
    items.forEach(function (i) {
      var key = i.date ? i.date.slice(0, 7) : "";
      if (!group || group.key !== key) {
        var p = /^(\d{4})-(\d{2})$/.exec(key);
        group = { key: key, body: el("tbody") };
        group.body.appendChild(el("tr", { "class": "month" },
          el("th", { colspan: "2", scope: "rowgroup" }, p ? p[1] + "년 " + (+p[2]) + "월" : "날짜 미상")));
        table.appendChild(group.body);
      }
      group.body.appendChild(row(i, false));
    });
  }

  function fail(err) {
    if (window.console) console.error("manifest", err);
    var note = byId("notice");
    if (note) {
      note.textContent = "발행 목록을 불러오지 못했습니다. 잠시 뒤 새로고침하거나 위·아래 메뉴로 각 발행물에 들어가세요.";
      note.hidden = false;
    }
    fill("lead-date", "-");
    var body = byId("ledger-body");
    if (body) body.textContent = "";
  }

  fetch(ROOT + "data/manifest.json", { cache: "no-cache" })
    .then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(function (m) {
      var items = ((m && m.items) || []).slice().sort(newestFirst);
      if (PAGE === "portal") renderPortal(items);
      else renderSeries(only(items, PAGE));
    })
    .catch(fail);
})();
