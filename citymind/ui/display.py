"""PyQt6 UI for CityMind - Neo-Urban Command Center aesthetic."""
import math
import random
from collections import deque
from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF, pyqtSignal, QThread
from PyQt6.QtGui import (
    QColor, QPen, QBrush, QFont, QPainter, QPainterPath, QLinearGradient,
    QRadialGradient, QPolygonF, QKeySequence, QShortcut, QFontDatabase,
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QSlider, QCheckBox, QGroupBox, QListWidget,
    QListWidgetItem, QGraphicsView, QGraphicsScene, QStatusBar, QMessageBox,
    QFrame, QFileDialog,
)

from core.city_graph import graph
from core.event_bus import (
    bus, ROAD_BLOCKED, ROAD_UNBLOCKED, RISK_UPDATED, AMBULANCE_MOVED,
    POLICE_MOVED, CIVILIAN_RESCUED, SIMULATION_STEP, REROUTE,
)
from challenges import c3_ambulance, c_police, c4_routing
from simulation import runner

# ---------------- Theme: NEO-URBAN COMMAND CENTER ----------------
THEME = {
    "bg":           "#05070D",
    "bg2":          "#080C14",
    "panel":        "#0C1018",
    "panel_alt":    "#111520",
    "border":       "#1A2232",
    "border_glow":  "#1E3A5F",
    "text":         "#D0E4F7",
    "text_dim":     "#5A7A99",
    "accent":       "#00B4FF",   # electric cyan
    "accent_glow":  "#5FD3FF",
    "accent2":      "#0066FF",
    "ok":           "#00FF9C",
    "warn":         "#FFB000",
    "danger":       "#FF3355",
    "purple":       "#9D4EDD",
    "cyan":         "#00B4FF",
    "gold":         "#FFD700",
    "grid_line":    "#0D1724",
    "road":         "#3A4458",
    "road_edge":    "#5A6678",
    "road_line":    "#E8C84A",
    "road_active":  "#00B4FF",
}

CELL_COLORS = {
    "Hospital":       "#FF2244",
    "School":         "#FFD700",
    "Industrial":     "#4A5568",
    "Residential":    "#1A6B3A",
    "PowerPlant":     "#FF7700",
    "AmbulanceDepot": "#005BFF",
    "Empty":          "#080C14",
}
CELL_LETTER = {
    "Hospital": "H", "School": "S", "Industrial": "I",
    "Residential": "R", "PowerPlant": "P", "AmbulanceDepot": "D",
    "Empty": "",
}
# Distinct, high-contrast risk colors
RISK_BORDER = {
    "High":   QColor(255, 70, 70),
    "Medium": QColor(255, 180, 60),
    "Low":    QColor(60, 220, 130),
}
RISK_FILL = {
    "High":   QColor(255, 60, 60, 130),
    "Medium": QColor(255, 170, 50, 90),
    "Low":    QColor(60, 220, 130, 40),
}
EVENT_COLOR = {
    ROAD_BLOCKED:    "#F85149",
    ROAD_UNBLOCKED:  "#3FB950",
    RISK_UPDATED:    "#F0883E",
    AMBULANCE_MOVED: "#39D0D8",
    POLICE_MOVED:    "#79C0FF",
    CIVILIAN_RESCUED:"#FFD60A",
    REROUTE:         "#BC8CFF",
    SIMULATION_STEP: "#8B95A7",
    "INIT":          "#8B95A7",
    "RESET":         "#8B95A7",
    "COMPLETE":      "#3FB950",
}

CELL_SIZE = 60
GRID = 10
PAD = 14


class InitThread(QThread):
    finished_ok = pyqtSignal()
    failed = pyqtSignal(str)

    def run(self):
        try:
            runner.initialize()
            self.finished_ok.emit()
        except Exception as e:
            import traceback; traceback.print_exc()
            self.failed.emit(str(e))


# ----------------- Grid Canvas -----------------
class GridCanvas(QGraphicsView):
    """Neo-urban command-center city grid with detailed building tiles,
    animated vehicles, and cinematic effects. All drawing in QPainter."""

    def __init__(self):
        super().__init__()
        self.scene_obj = QGraphicsScene(self)
        self.setScene(self.scene_obj)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.overlays = {
            "roads": True,
            "ambulance_coverage": False,
            "crime_heatmap": True,
            "police_zones": False,
            "astar": True,
            "density": False,
        }
        self.pulse = 0.0
        # ambulance smooth animation state — list of dicts:
        #   {"node": int, "x": float, "y": float,
        #    "trail": deque(maxlen=8), "heading": float}
        self._amb_render = []
        # team trail (last few node ids)
        self._team_trail = []
        self._last_team = None
        # smoke particles for industrial chimneys: cid -> list[(x, y, age)]
        self._smoke = {}
        # cached intersection nodes (computed once per re-init)
        self._intersections_cache = None
        self._intersections_size = 0
        # data-rain decoration (for empty space)
        self._rain = []
        for _ in range(40):
            self._rain.append([
                random.uniform(0, GRID * CELL_SIZE),
                random.uniform(0, GRID * CELL_SIZE),
                random.choice("0123456789ABCDEF"),
                random.uniform(0, 1),
            ])
        self._build_size()

    def _build_size(self):
        w = GRID * CELL_SIZE + PAD * 2
        h = GRID * CELL_SIZE + PAD * 2
        self.scene_obj.setSceneRect(0, 0, w, h)
        # Allow the view to shrink below the scene's natural size — the
        # auto-fit code below will scale the scene to match the viewport.
        self.setMinimumSize(240, 240)
        # Zoom multiplier applied on TOP of fit-to-view scaling.
        # 1.0 = whole map visible; >1.0 = zoom in.
        self._user_zoom = 1.0
        self._auto_fit = True

    # ---------------- Zoom / Fit ----------------
    def set_zoom(self, factor: float):
        """Set user zoom multiplier (>=1.0). Called by the zoom slider."""
        self._user_zoom = max(0.5, min(3.0, float(factor)))
        self._apply_view_transform()

    def fit_map(self):
        """Reset zoom and re-fit the entire city into view."""
        self._user_zoom = 1.0
        self._auto_fit = True
        self._apply_view_transform()

    def _apply_view_transform(self):
        """Scale the view so the full scene fits, then apply user zoom."""
        self.resetTransform()
        if not self.viewport():
            return
        vw = max(1, self.viewport().width())
        vh = max(1, self.viewport().height())
        sr = self.scene_obj.sceneRect()
        if sr.width() <= 0 or sr.height() <= 0:
            return
        fit = min(vw / sr.width(), vh / sr.height())
        s = fit * self._user_zoom
        self.scale(s, s)
        # Centre the scene in the view.
        self.centerOn(sr.center())
        # Show scrollbars only when zoomed past the fit point.
        policy = (Qt.ScrollBarPolicy.ScrollBarAsNeeded
                  if self._user_zoom > 1.0
                  else Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(policy)
        self.setVerticalScrollBarPolicy(policy)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._apply_view_transform()

    def wheelEvent(self, ev):
        # Ctrl + wheel to zoom, otherwise ignore (we don't want to scroll).
        if ev.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = ev.angleDelta().y()
            step = 0.1 if delta > 0 else -0.1
            self.set_zoom(self._user_zoom + step)
            ev.accept()
            return
        ev.ignore()

    def cell_rect(self, r, c):
        return QRectF(PAD + c * CELL_SIZE, PAD + r * CELL_SIZE, CELL_SIZE, CELL_SIZE)

    def cell_center(self, r, c):
        return QPointF(PAD + c * CELL_SIZE + CELL_SIZE / 2,
                       PAD + r * CELL_SIZE + CELL_SIZE / 2)

    def set_overlay(self, key, val):
        self.overlays[key] = val
        self.viewport().update()

    # ============== BACKGROUND ==============
    def drawBackground(self, painter: QPainter, rect):
        # Deep space gradient
        grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        grad.setColorAt(0, QColor(THEME["bg"]))
        grad.setColorAt(1, QColor(THEME["bg2"]))
        painter.fillRect(rect, QBrush(grad))

        # Subtle perspective grid hint — kept very faint so it can't be
        # confused with the actual road network. Only the corners get a
        # whisper of converging lines.
        sr = self.scene_obj.sceneRect()
        faint = QColor(THEME["grid_line"])
        faint.setAlpha(70)
        painter.setPen(QPen(faint, 1))
        for i in range(0, 5):
            x = sr.left() + i * (sr.width() / 12)
            painter.drawLine(QPointF(x, sr.bottom()), QPointF(sr.left(), sr.top()))
            x2 = sr.right() - i * (sr.width() / 12)
            painter.drawLine(QPointF(x2, sr.bottom()), QPointF(sr.right(), sr.top()))

        # CRT scanlines — every 3 px
        painter.setPen(QPen(QColor(0, 0, 0, 30), 1))
        y = int(rect.top())
        end = int(rect.bottom())
        while y < end:
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            y += 3

        # Vignette
        vg = QRadialGradient(sr.center(), max(sr.width(), sr.height()) * 0.7)
        vg.setColorAt(0, QColor(0, 0, 0, 0))
        vg.setColorAt(0.7, QColor(0, 0, 0, 90))
        vg.setColorAt(1, QColor(THEME["bg"]))
        painter.setBrush(QBrush(vg))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(rect)

    # ============== AMBULANCE ANIMATION ==============
    def _animate_ambulance_targets(self):
        """Smoothly move ambulance render positions toward target node.
        Track heading angle and an 8-position trail."""
        targets = c3_ambulance.get_positions()
        new_render = []
        for i, t in enumerate(targets):
            if t not in graph.g.nodes:
                continue
            tgt_pt = self.cell_center(*graph.get_node(t)["grid_pos"])
            tx, ty = tgt_pt.x(), tgt_pt.y()
            if i < len(self._amb_render):
                prev = self._amb_render[i]
                cx, cy = prev["x"], prev["y"]
                trail = prev["trail"]
                heading = prev["heading"]
                dx, dy = tx - cx, ty - cy
                dist = math.hypot(dx, dy)
                if dist > 0.5:
                    # Update heading from movement direction
                    heading = math.degrees(math.atan2(dy, dx))
                    # Append to trail every few pixels
                    if not trail or math.hypot(cx - trail[-1][0], cy - trail[-1][1]) > 4:
                        trail.append((cx, cy))
                cx += dx * 0.15
                cy += dy * 0.15
            else:
                cx, cy = tx, ty
                trail = deque(maxlen=8)
                heading = 0.0
            new_render.append({
                "node": t, "x": cx, "y": cy,
                "trail": trail, "heading": heading,
            })
        self._amb_render = new_render

    # ============== INTERSECTIONS ==============
    def _intersections(self):
        if (self._intersections_cache is not None and
                self._intersections_size == graph.g.number_of_nodes()):
            return self._intersections_cache
        out = set()
        for n in graph.g.nodes():
            if graph.g.degree(n) >= 3:
                out.add(n)
        self._intersections_cache = out
        self._intersections_size = graph.g.number_of_nodes()
        return out

    # ============== FOREGROUND ==============
    def drawForeground(self, painter: QPainter, rect):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.pulse += 0.08
        if self.pulse > math.tau:
            self.pulse -= math.tau

        # Boot screen if not initialized
        if not graph.all_nodes():
            self._draw_boot_sequence(painter)
            return

        pulse_amt = 0.5 + 0.5 * math.sin(self.pulse)

        # 1) Roads (drawn FIRST, under buildings, so streets feel like
        #    infrastructure rather than overlays)
        if self.overlays["roads"]:
            self._draw_road_network(painter, pulse_amt)

        # 2) Building tiles
        for r in range(GRID):
            for c in range(GRID):
                cid = r * GRID + c
                if cid not in graph.g.nodes:
                    continue
                d = graph.get_node(cid)
                t = d["location_type"]
                rect_c = self.cell_rect(r, c)
                inner = rect_c.adjusted(3, 3, -3, -3)
                self._draw_tile(painter, cid, d, t, rect_c, inner, pulse_amt)

        # 3) Density bars (over tiles)
        if self.overlays["density"]:
            for r in range(GRID):
                for c in range(GRID):
                    cid = r * GRID + c
                    if cid not in graph.g.nodes:
                        continue
                    d = graph.get_node(cid)
                    if d["location_type"] == "Empty":
                        continue
                    self._draw_density_bar(painter, self.cell_rect(r, c),
                                           d["population_density"])

        # 4) Risk overlay (heat shimmer)
        if self.overlays["crime_heatmap"]:
            for r in range(GRID):
                for c in range(GRID):
                    cid = r * GRID + c
                    if cid not in graph.g.nodes:
                        continue
                    d = graph.get_node(cid)
                    if d["location_type"] == "Empty":
                        continue
                    self._draw_risk_overlay(painter, self.cell_rect(r, c),
                                            d["predicted_risk"], pulse_amt)

        # 5) Ambulance coverage (sonar pulse rings)
        if self.overlays["ambulance_coverage"]:
            self._draw_coverage_overlay(painter, pulse_amt)

        # 6) Police zones (radial glow)
        if self.overlays["police_zones"]:
            for n in c_police.get_positions():
                if n not in graph.g.nodes:
                    continue
                ctr = self.cell_center(*graph.get_node(n)["grid_pos"])
                pg = QRadialGradient(ctr, CELL_SIZE * 1.6)
                pg.setColorAt(0, QColor(0, 180, 255, 70))
                pg.setColorAt(1, QColor(0, 180, 255, 0))
                painter.setBrush(QBrush(pg))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(ctr, CELL_SIZE * 1.6, CELL_SIZE * 1.6)

        # 7) A* path (animated cyan with glow + traveling dash)
        if self.overlays["astar"]:
            self._draw_astar_path(painter, pulse_amt)

        # 8) Police officers (corner of cell so it doesn't cover building)
        for n in c_police.get_positions():
            if n not in graph.g.nodes:
                continue
            r, c = graph.get_node(n)["grid_pos"]
            cr = self.cell_rect(r, c)
            cx = cr.right() - 12
            cy = cr.top() + 14
            risk = graph.get_node(n).get("predicted_risk", "Low")
            self._draw_police_officer(painter, cx, cy, self.pulse, risk)

        # 9) Civilians (SOS distress markers)
        rescued = set(c4_routing.get_rescued())
        target = c4_routing.get_current_target()
        for n in c4_routing.get_civilians():
            if n not in graph.g.nodes:
                continue
            ctr = self.cell_center(*graph.get_node(n)["grid_pos"])
            done = n in rescued
            is_target = (n == target)
            self._draw_civilian(painter, ctr.x(), ctr.y(),
                                pulse_amt, done, is_target)

        # 10) Ambulances (detailed vehicles with trail)
        self._animate_ambulance_targets()
        for i, amb in enumerate(self._amb_render):
            # Trail
            trail = list(amb["trail"])
            for ti, (px, py) in enumerate(trail):
                alpha = int(120 * (ti + 1) / max(len(trail), 1))
                painter.setBrush(QBrush(QColor(0, 180, 255, alpha)))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(QPointF(px, py), 2.0, 2.0)
            # Active = repositioning (target moved very recently)
            is_active = bool(trail) and len(trail) > 0
            self._draw_ambulance(painter, amb["x"], amb["y"],
                                 amb["heading"], is_active, self.pulse, i + 1)

        # 11) Medical team
        team = c4_routing.get_team_position()
        if team is not None and team in graph.g.nodes:
            if team != self._last_team:
                if self._last_team is not None:
                    self._team_trail.append(self._last_team)
                    if len(self._team_trail) > 6:
                        self._team_trail.pop(0)
                self._last_team = team
            for ti, tn in enumerate(self._team_trail):
                if tn not in graph.g.nodes:
                    continue
                ctr = self.cell_center(*graph.get_node(tn)["grid_pos"])
                alpha = int(40 + ti * 25)
                painter.setBrush(QBrush(QColor(0, 180, 255, alpha)))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(ctr, 4, 4)
            ctr = self.cell_center(*graph.get_node(team)["grid_pos"])
            grad = QRadialGradient(ctr, 14)
            grad.setColorAt(0, QColor(255, 255, 255, 240))
            grad.setColorAt(1, QColor(THEME["cyan"]))
            painter.setBrush(QBrush(grad))
            painter.setPen(QPen(QColor(THEME["cyan"]), 1.8))
            painter.drawEllipse(ctr, 7, 7)

    # ============== TILE DISPATCH ==============
    def _draw_tile(self, painter, cid, d, t, rect_c, inner, pulse):
        if t == "Empty":
            self._draw_empty_tile(painter, rect_c, inner, cid)
        elif t == "Hospital":
            self._draw_hospital_tile(painter, inner, cid, pulse)
        elif t == "School":
            self._draw_school_tile(painter, inner, cid)
        elif t == "Industrial":
            self._draw_industrial_tile(painter, inner, cid, pulse,
                                       d.get("predicted_risk", "Low"))
        elif t == "Residential":
            self._draw_residential_tile(painter, inner, cid)
        elif t == "PowerPlant":
            self._draw_powerplant_tile(painter, inner, cid, pulse)
        elif t == "AmbulanceDepot":
            self._draw_depot_tile(painter, inner, cid, pulse)

    # ============== TILE DRAWERS ==============
    def _draw_empty_tile(self, painter, rect_c, inner, cid):
        # Empty cells are kept fully transparent so roads passing through
        # them remain visually continuous. Only a tiny coordinate label is
        # drawn in the corner — and only for cells that have NO road on
        # them (degree 0), so we never interrupt a road.
        if graph.g.degree(cid) > 0:
            return
        r, c = divmod(cid, GRID)
        painter.setPen(QPen(QColor(THEME["grid_line"]).lighter(180)))
        painter.setFont(QFont("Courier New", 6))
        painter.drawText(inner.adjusted(3, 0, 0, -3),
                         Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft,
                         f"{r:02d},{c:02d}")

    def _draw_hospital_tile(self, painter, inner, cid, pulse):
        # Pulsing red glow halo
        ctr = inner.center()
        glow_r = inner.width() * 0.7 + 4 * pulse
        glow = QRadialGradient(ctr, glow_r)
        a = int(40 + 30 * pulse)
        glow.setColorAt(0, QColor(255, 50, 80, a))
        glow.setColorAt(1, QColor(255, 50, 80, 0))
        painter.setBrush(QBrush(glow))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(ctr, glow_r, glow_r)

        # Crimson body gradient
        grad = QLinearGradient(inner.topLeft(), inner.bottomRight())
        grad.setColorAt(0, QColor("#8B0000"))
        grad.setColorAt(1, QColor("#FF2244"))
        painter.setBrush(QBrush(grad))
        painter.setPen(QPen(QColor(THEME["border_glow"]), 1))
        painter.drawRoundedRect(inner, 6, 6)

        # Window grid (subtle dark lines)
        painter.setPen(QPen(QColor(0, 0, 0, 80), 1))
        for i in range(1, 4):
            x = inner.left() + i * inner.width() / 4
            painter.drawLine(QPointF(x, inner.top() + 8),
                             QPointF(x, inner.bottom() - 8))
        for i in range(1, 3):
            y = inner.top() + i * inner.height() / 3
            painter.drawLine(QPointF(inner.left() + 4, y),
                             QPointF(inner.right() - 4, y))

        # Big white cross centered
        cw = inner.width() * 0.45
        ch = inner.height() * 0.12
        painter.setBrush(QBrush(QColor(255, 255, 255, 240)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QRectF(ctr.x() - cw / 2, ctr.y() - ch / 2, cw, ch), 2, 2)
        painter.drawRoundedRect(QRectF(ctr.x() - ch / 2, ctr.y() - cw / 2, ch, cw), 2, 2)

        # Helipad "H" on roof area (top edge)
        painter.setPen(QPen(QColor(255, 255, 255, 180)))
        painter.setFont(QFont("Courier New", 6, QFont.Weight.Bold))
        painter.drawText(QRectF(inner.left(), inner.top() + 1, inner.width(), 8),
                         Qt.AlignmentFlag.AlignHCenter, "▣ H")

        # Bottom label
        painter.setPen(QPen(QColor(255, 255, 255, 220)))
        painter.setFont(QFont("Courier New", 6, QFont.Weight.Bold))
        painter.drawText(inner.adjusted(0, 0, 0, -1),
                         Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
                         "HOSP")

    def _draw_school_tile(self, painter, inner, cid):
        grad = QLinearGradient(inner.topLeft(), inner.bottomRight())
        grad.setColorAt(0, QColor("#7A5F00"))
        grad.setColorAt(1, QColor("#FFD700"))
        painter.setBrush(QBrush(grad))
        painter.setPen(QPen(QColor(THEME["border"]), 1))
        painter.drawRoundedRect(inner, 6, 6)

        # Brick texture: faint horizontal lines
        painter.setPen(QPen(QColor(0, 0, 0, 50), 1))
        for i in range(1, 6):
            y = inner.top() + i * inner.height() / 6
            painter.drawLine(QPointF(inner.left() + 3, y),
                             QPointF(inner.right() - 3, y))

        # Graduation cap
        ctr = inner.center()
        cap_w = inner.width() * 0.5
        cap_y = ctr.y() - 4
        # cap base diamond
        cap = QPolygonF([
            QPointF(ctr.x() - cap_w / 2, cap_y),
            QPointF(ctr.x(), cap_y - cap_w / 4),
            QPointF(ctr.x() + cap_w / 2, cap_y),
            QPointF(ctr.x(), cap_y + cap_w / 4),
        ])
        painter.setBrush(QBrush(QColor("#1A1A1A")))
        painter.setPen(QPen(QColor("#000000"), 0.8))
        painter.drawPolygon(cap)
        # tassel
        painter.setPen(QPen(QColor("#FFD700"), 1.5))
        painter.drawLine(QPointF(ctr.x() + cap_w / 2 - 2, cap_y),
                         QPointF(ctr.x() + cap_w / 2 + 2, cap_y + 6))

        painter.setPen(QPen(QColor(0, 0, 0, 200)))
        painter.setFont(QFont("Courier New", 6, QFont.Weight.Bold))
        painter.drawText(inner.adjusted(0, 0, 0, -1),
                         Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
                         "SCH")

    def _draw_industrial_tile(self, painter, inner, cid, pulse, risk):
        grad = QLinearGradient(inner.topLeft(), inner.bottomRight())
        grad.setColorAt(0, QColor("#1C2030"))
        grad.setColorAt(1, QColor("#4A5568"))
        painter.setBrush(QBrush(grad))
        painter.setPen(QPen(QColor(THEME["border"]), 1))
        painter.drawRoundedRect(inner, 4, 4)

        # Yellow warning glow if high risk
        if risk == "High":
            wg = QRadialGradient(inner.center(), inner.width() * 0.7)
            a = int(40 + 25 * pulse)
            wg.setColorAt(0, QColor(255, 180, 0, a))
            wg.setColorAt(1, QColor(255, 180, 0, 0))
            painter.setBrush(QBrush(wg))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(inner.center(), inner.width() * 0.7, inner.width() * 0.7)

        # Chimney (tall narrow rect on top edge)
        chim_x = inner.left() + inner.width() * 0.62
        chim_w = 5
        chim_h = inner.height() * 0.45
        chim = QRectF(chim_x, inner.top() + 4, chim_w, chim_h)
        painter.setBrush(QBrush(QColor("#2A3140")))
        painter.setPen(QPen(QColor("#0A0D14"), 1))
        painter.drawRect(chim)
        # red stripe near top of chimney
        painter.setBrush(QBrush(QColor("#FF3355")))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(QRectF(chim_x, inner.top() + 6, chim_w, 1.5))

        # Smoke particles emanating from chimney top — strictly clipped
        # INSIDE the cell so they don't streak up into the cell above
        # (which previously made them look like weird road segments).
        painter.save()
        painter.setClipRect(inner)
        smoke = self._smoke.setdefault(cid, [])
        if random.random() < 0.35:
            smoke.append([chim_x + chim_w / 2, inner.top() + 5, 0])
        new_smoke = []
        for sp in smoke:
            sp[0] += random.uniform(-0.3, 0.3)
            sp[1] -= 0.4
            sp[2] += 1
            # cap lifetime so smoke fades out before reaching cell top
            if sp[2] < 14 and sp[1] > inner.top():
                new_smoke.append(sp)
                a = max(0, int(110 - sp[2] * 7))
                r = 1.2 + sp[2] * 0.08
                painter.setBrush(QBrush(QColor(180, 180, 180, a)))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(QPointF(sp[0], sp[1]), r, r)
        self._smoke[cid] = new_smoke
        painter.restore()

        # Diagonal hazard stripes at bottom
        strip_y = inner.bottom() - 7
        strip_h = 4
        painter.setPen(Qt.PenStyle.NoPen)
        x = inner.left()
        idx = 0
        while x < inner.right():
            col = QColor("#FFB000") if idx % 2 == 0 else QColor("#1C2030")
            painter.setBrush(QBrush(col))
            painter.drawRect(QRectF(x, strip_y, 4, strip_h))
            x += 4
            idx += 1

        painter.setPen(QPen(QColor(255, 255, 255, 200)))
        painter.setFont(QFont("Courier New", 6, QFont.Weight.Bold))
        painter.drawText(inner.adjusted(0, 4, 0, -10),
                         Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
                         "IND")

    def _draw_residential_tile(self, painter, inner, cid):
        # Slight per-tile lightness variation
        var = (hash(cid) % 21) - 10
        base_a = QColor("#0A3D1F")
        base_b = QColor("#1A6B3A")
        base_b.setHsv(base_b.hue(), base_b.saturation(),
                      max(0, min(255, base_b.value() + var)))
        grad = QLinearGradient(inner.topLeft(), inner.bottomRight())
        grad.setColorAt(0, base_a)
        grad.setColorAt(1, base_b)
        painter.setBrush(QBrush(grad))
        painter.setPen(QPen(QColor(THEME["border"]), 1))
        painter.drawRoundedRect(inner, 5, 5)

        # House silhouette: triangle roof + body + door
        ctr = inner.center()
        house_w = inner.width() * 0.52
        house_h = inner.height() * 0.32
        body_top = ctr.y() - house_h / 4
        body = QRectF(ctr.x() - house_w / 2, body_top, house_w, house_h)
        painter.setBrush(QBrush(QColor("#E8DCC4")))
        painter.setPen(QPen(QColor("#000000"), 0.8))
        painter.drawRect(body)

        # Roof
        roof_color = QColor("#8B4513") if cid % 2 == 0 else QColor("#2F4F4F")
        roof = QPolygonF([
            QPointF(ctr.x() - house_w / 2 - 2, body_top),
            QPointF(ctr.x() + house_w / 2 + 2, body_top),
            QPointF(ctr.x(), body_top - house_h * 0.55),
        ])
        painter.setBrush(QBrush(roof_color))
        painter.setPen(QPen(QColor("#000000"), 0.8))
        painter.drawPolygon(roof)

        # Door
        door_w = house_w * 0.20
        door_h = house_h * 0.5
        painter.setBrush(QBrush(QColor("#3A2A1A")))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(QRectF(ctr.x() - door_w / 2,
                                body.bottom() - door_h, door_w, door_h))

        # Windows (lit yellow squares)
        win_size = 3
        painter.setBrush(QBrush(QColor("#FFE066")))
        painter.setPen(QPen(QColor("#FFB000"), 0.6))
        for ox in (-house_w * 0.28, house_w * 0.28):
            painter.drawRect(QRectF(ctr.x() + ox - win_size / 2,
                                    body_top + 4, win_size, win_size))

        # Label
        painter.setPen(QPen(QColor(220, 240, 230, 200)))
        painter.setFont(QFont("Courier New", 5, QFont.Weight.Bold))
        painter.drawText(inner.adjusted(0, 0, 0, -1),
                         Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
                         "RES")

    def _draw_powerplant_tile(self, painter, inner, cid, pulse):
        grad = QLinearGradient(inner.topLeft(), inner.bottomRight())
        grad.setColorAt(0, QColor("#3D1A00"))
        grad.setColorAt(1, QColor("#FF7700"))
        painter.setBrush(QBrush(grad))
        painter.setPen(QPen(QColor(THEME["border"]), 1))
        painter.drawRoundedRect(inner, 4, 4)

        # Orange glow halo
        glow = QRadialGradient(inner.center(), inner.width() * 0.7)
        a = int(35 + 25 * pulse)
        glow.setColorAt(0, QColor(255, 140, 0, a))
        glow.setColorAt(1, QColor(255, 140, 0, 0))
        painter.setBrush(QBrush(glow))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(inner.center(), inner.width() * 0.7, inner.width() * 0.7)

        # Cooling tower (trapezoid)
        ctr = inner.center()
        tw_top = inner.width() * 0.22
        tw_bot = inner.width() * 0.42
        tw_h = inner.height() * 0.55
        top_y = ctr.y() - tw_h * 0.35
        bot_y = top_y + tw_h
        tower = QPolygonF([
            QPointF(ctr.x() - tw_top / 2, top_y),
            QPointF(ctr.x() + tw_top / 2, top_y),
            QPointF(ctr.x() + tw_bot / 2, bot_y),
            QPointF(ctr.x() - tw_bot / 2, bot_y),
        ])
        painter.setBrush(QBrush(QColor("#2A2218")))
        painter.setPen(QPen(QColor("#000000"), 1))
        painter.drawPolygon(tower)

        # Heat shimmer (wavy lines above tower)
        painter.setPen(QPen(QColor(255, 200, 100, 140), 1))
        for i in range(3):
            phase = self.pulse + i * 0.7
            y_off = top_y - 2 - i * 3
            path = QPainterPath()
            path.moveTo(ctr.x() - tw_top / 2, y_off)
            for k in range(5):
                px = ctr.x() - tw_top / 2 + k * tw_top / 4
                py = y_off - 2 * math.sin(phase + k)
                path.lineTo(px, py)
            painter.drawPath(path)

        # Lightning bolt
        bolt = QPainterPath()
        bx = inner.left() + 4
        by = inner.top() + 4
        bolt.moveTo(bx + 4, by)
        bolt.lineTo(bx, by + 5)
        bolt.lineTo(bx + 3, by + 5)
        bolt.lineTo(bx, by + 10)
        bolt.lineTo(bx + 6, by + 4)
        bolt.lineTo(bx + 3, by + 4)
        bolt.lineTo(bx + 5, by)
        bolt.closeSubpath()
        painter.setBrush(QBrush(QColor("#FFD700")))
        painter.setPen(QPen(QColor("#FF7700"), 0.8))
        painter.drawPath(bolt)

        painter.setPen(QPen(QColor(255, 255, 255, 220)))
        painter.setFont(QFont("Courier New", 6, QFont.Weight.Bold))
        painter.drawText(inner.adjusted(0, 0, 0, -1),
                         Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
                         "PWR")

    def _draw_depot_tile(self, painter, inner, cid, pulse):
        grad = QLinearGradient(inner.topLeft(), inner.bottomRight())
        grad.setColorAt(0, QColor("#001433"))
        grad.setColorAt(1, QColor("#005BFF"))
        painter.setBrush(QBrush(grad))
        painter.setPen(QPen(QColor(THEME["border_glow"]), 1))
        painter.drawRoundedRect(inner, 5, 5)

        # Garage door (horizontal stripes bottom half)
        door_y = inner.center().y()
        painter.setPen(QPen(QColor(0, 0, 0, 130), 1))
        for i in range(5):
            y = door_y + (i + 1) * (inner.bottom() - door_y) / 6
            painter.drawLine(QPointF(inner.left() + 4, y),
                             QPointF(inner.right() - 4, y))

        # Rotating blue radar sweep
        ctr = QPointF(inner.center().x(), inner.top() + inner.height() * 0.32)
        sweep_r = inner.width() * 0.30
        sweep_angle = (self.pulse * 60) % 360
        # Faint disc
        painter.setBrush(QBrush(QColor(0, 100, 255, 50)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(ctr, sweep_r, sweep_r)
        # Sweep line
        painter.setPen(QPen(QColor(80, 200, 255, 220), 1.5))
        end = QPointF(
            ctr.x() + sweep_r * math.cos(math.radians(sweep_angle)),
            ctr.y() + sweep_r * math.sin(math.radians(sweep_angle)),
        )
        painter.drawLine(ctr, end)
        # Center dot
        painter.setBrush(QBrush(QColor("#80E5FF")))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(ctr, 1.6, 1.6)

        painter.setPen(QPen(QColor(220, 240, 255, 230)))
        painter.setFont(QFont("Courier New", 6, QFont.Weight.Bold))
        painter.drawText(inner.adjusted(0, 0, 0, -1),
                         Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
                         "DEPOT")

    # ============== ROAD NETWORK ==============
    def _draw_road_network(self, painter, pulse):
        intersections = self._intersections()
        # Pre-compute centers once
        edges = []
        for u, v, dd in graph.g.edges(data=True):
            a = self.cell_center(*graph.get_node(u)["grid_pos"])
            b = self.cell_center(*graph.get_node(v)["grid_pos"])
            edges.append((u, v, a, b, dd))

        # Phase 0: pavement pad under any cell that has a road on it.
        # This gives empty cells a visible "asphalt square" so the road
        # never looks like it's floating across nothing.
        pad_brush = QBrush(QColor(THEME["road"]).darker(115))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(pad_brush)
        for n in graph.g.nodes():
            if graph.g.degree(n) == 0:
                continue
            d = graph.get_node(n)
            if d.get("location_type") != "Empty":
                continue
            r, c = d["grid_pos"]
            cr = self.cell_rect(r, c)
            painter.drawRoundedRect(cr.adjusted(6, 6, -6, -6), 3, 3)

        # Phase 1: dark road shoulder (wider, slightly darker outline)
        shoulder_pen = QPen(QColor(THEME["road"]).darker(140), 11,
                            Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(shoulder_pen)
        for u, v, a, b, dd in edges:
            painter.drawLine(a, b)

        # Phase 2: asphalt main lane
        asphalt_pen = QPen(QColor(THEME["road"]), 9,
                           Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(asphalt_pen)
        for u, v, a, b, dd in edges:
            painter.drawLine(a, b)

        # Phase 3: subtle lane edge highlight (top edge of asphalt)
        edge_pen = QPen(QColor(THEME["road_edge"]), 1,
                        Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        edge_pen.setCosmetic(True)
        painter.setPen(edge_pen)
        for u, v, a, b, dd in edges:
            painter.drawLine(a, b)

        # Phase 4: yellow dashed centerline (classic road marking)
        center_pen = QPen(QColor(THEME["road_line"]), 1.4,
                          Qt.PenStyle.CustomDashLine)
        center_pen.setDashPattern([4, 4])
        center_pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(center_pen)
        for u, v, a, b, dd in edges:
            if dd.get("is_blocked"):
                continue
            painter.drawLine(a, b)
        # Phase 3: blocked road X marks + warning
        for u, v, dd in graph.g.edges(data=True):
            if not dd.get("is_blocked"):
                continue
            a = self.cell_center(*graph.get_node(u)["grid_pos"])
            b = self.cell_center(*graph.get_node(v)["grid_pos"])
            mid = QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2)
            # red X
            x_pen = QPen(QColor(THEME["danger"]), 3)
            x_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(x_pen)
            painter.drawLine(QPointF(mid.x() - 6, mid.y() - 6),
                             QPointF(mid.x() + 6, mid.y() + 6))
            painter.drawLine(QPointF(mid.x() - 6, mid.y() + 6),
                             QPointF(mid.x() + 6, mid.y() - 6))
            # pulsing red glow
            ga = int(40 + 50 * pulse)
            glow = QRadialGradient(mid, 16)
            glow.setColorAt(0, QColor(255, 50, 80, ga))
            glow.setColorAt(1, QColor(255, 50, 80, 0))
            painter.setBrush(QBrush(glow))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(mid, 16, 16)
        # Phase 4: intersections (lighter squares)
        painter.setBrush(QBrush(QColor("#1E2E44")))
        painter.setPen(Qt.PenStyle.NoPen)
        for n in intersections:
            ctr = self.cell_center(*graph.get_node(n)["grid_pos"])
            painter.drawRect(QRectF(ctr.x() - 4, ctr.y() - 4, 8, 8))

    def _draw_astar_path(self, painter, pulse):
        path = c4_routing.get_current_path()
        if not path or len(path) < 2:
            return
        pts = [self.cell_center(*graph.get_node(n)["grid_pos"]) for n in path]
        # Multi-layer glow
        for w, alpha in ((12, 25), (8, 50), (5, 100)):
            pen = QPen(QColor(0, 180, 255, alpha), w)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            for i in range(len(pts) - 1):
                painter.drawLine(pts[i], pts[i + 1])
        # Animated dashed cyan line on top
        dash_pen = QPen(QColor(THEME["accent"]), 2.5, Qt.PenStyle.CustomDashLine)
        dash_pen.setDashPattern([6, 4])
        # Travel offset based on pulse — gives the dash a flowing motion
        dash_pen.setDashOffset((self.pulse * 12) % 10)
        dash_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(dash_pen)
        for i in range(len(pts) - 1):
            painter.drawLine(pts[i], pts[i + 1])

    # ============== AMBULANCE / POLICE / CIVILIAN ==============
    def _draw_ambulance(self, painter, cx, cy, heading, is_active, pulse, idx):
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(heading)

        # Outer rotating glow
        if is_active:
            glow = QRadialGradient(QPointF(0, 0), 26)
            siren_r = int(255 if math.sin(pulse * 2) > 0 else 60)
            siren_b = 255 - siren_r
            glow.setColorAt(0, QColor(siren_r, 30, siren_b, 70))
            glow.setColorAt(1, QColor(siren_r, 30, siren_b, 0))
            painter.setBrush(QBrush(glow))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(0, 0), 26, 26)

        # Body
        body = QRectF(-13, -7, 26, 14)
        painter.setBrush(QBrush(QColor("#FFFFFF")))
        painter.setPen(QPen(QColor("#A0A8B0"), 0.7))
        painter.drawRoundedRect(body, 3, 3)

        # Red side stripe
        painter.setBrush(QBrush(QColor("#FF2244")))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(QRectF(-13, -1.5, 26, 3))

        # Cross (red box body — white cross inside)
        painter.setBrush(QBrush(QColor("#FF2244")))
        painter.drawRoundedRect(QRectF(-12, -6, 7, 12), 1, 1)
        painter.setBrush(QBrush(QColor("#FFFFFF")))
        painter.drawRect(QRectF(-11, -1, 5, 2))
        painter.drawRect(QRectF(-9.5, -4.5, 2, 9))

        # Windshield
        painter.setBrush(QBrush(QColor(30, 60, 120, 200)))
        painter.setPen(QPen(QColor("#5588CC"), 0.6))
        painter.drawRoundedRect(QRectF(5, -5.5, 7, 11), 1.5, 1.5)

        # Wheels
        painter.setBrush(QBrush(QColor("#222222")))
        painter.setPen(Qt.PenStyle.NoPen)
        for wx, wy in [(-7, -8), (-7, 8), (5, -8), (5, 8)]:
            painter.drawEllipse(QPointF(wx, wy), 2.5, 1.8)
            painter.setBrush(QBrush(QColor("#888888")))
            painter.drawEllipse(QPointF(wx, wy), 1.0, 0.7)
            painter.setBrush(QBrush(QColor("#222222")))

        # Lightbar (red+blue alternating)
        red_a = int(160 + 95 * (math.sin(pulse * 4) * 0.5 + 0.5)) if is_active else 80
        blue_a = int(160 + 95 * (math.cos(pulse * 4) * 0.5 + 0.5)) if is_active else 80
        painter.setBrush(QBrush(QColor(255, 30, 50, red_a)))
        painter.drawRoundedRect(QRectF(-4, -10, 4, 3), 1, 1)
        painter.setBrush(QBrush(QColor(30, 100, 255, blue_a)))
        painter.drawRoundedRect(QRectF(0, -10, 4, 3), 1, 1)

        painter.restore()

        # Coverage ring (drawn unrotated, only when active)
        if is_active:
            painter.setPen(QPen(QColor(0, 180, 255, 60), 1, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(cx, cy), CELL_SIZE * 2.4, CELL_SIZE * 2.4)

        # Label below
        painter.setPen(QPen(QColor(THEME["accent_glow"])))
        painter.setFont(QFont("Courier New", 6, QFont.Weight.Bold))
        painter.drawText(QRectF(cx - 16, cy + 13, 32, 8),
                         Qt.AlignmentFlag.AlignCenter, f"AMB-{idx}")

    def _draw_police_officer(self, painter, cx, cy, pulse, alert_level):
        painter.save()
        painter.translate(cx, cy)
        # Shadow
        painter.setBrush(QBrush(QColor(0, 0, 0, 60)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(0, 6), 7, 2.5)
        # Body
        painter.setBrush(QBrush(QColor("#1A237E")))
        painter.setPen(QPen(QColor("#0D1B2A"), 0.6))
        painter.drawRoundedRect(QRectF(-4.5, -3.5, 9, 9), 1.5, 1.5)
        # Head
        painter.setBrush(QBrush(QColor("#FDBCB4")))
        painter.drawEllipse(QPointF(0, -7), 4, 4)
        # Hat
        hat = QPainterPath()
        hat.moveTo(-5, -8.5)
        hat.lineTo(5, -8.5)
        hat.lineTo(3.5, -12)
        hat.lineTo(-3.5, -12)
        hat.closeSubpath()
        painter.setBrush(QBrush(QColor("#0D1B2A")))
        painter.drawPath(hat)
        # Hat band
        painter.setBrush(QBrush(QColor("#FFD700")))
        painter.drawRect(QRectF(-5, -9, 10, 1))
        # Badge (small star)
        badge_pts = []
        for i in range(10):
            ang = math.radians(i * 36 - 90)
            r = 2.0 if i % 2 == 0 else 0.9
            badge_pts.append(QPointF(r * math.cos(ang), r * math.sin(ang)))
        painter.setBrush(QBrush(QColor("#FFD700")))
        painter.setPen(QPen(QColor("#B8860B"), 0.5))
        painter.drawPolygon(QPolygonF(badge_pts))
        painter.restore()

        # Alert ring on high-risk zones
        if alert_level == "High":
            ra = int(80 + 80 * (math.sin(pulse * 4) * 0.5 + 0.5))
            painter.setPen(QPen(QColor(255, 60, 80, ra), 1.4))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(cx, cy), 11, 11)

    def _draw_civilian(self, painter, cx, cy, pulse, done, is_target):
        if done:
            # Subtle green checkmark badge
            painter.setBrush(QBrush(QColor(0, 255, 156, 200)))
            painter.setPen(QPen(QColor("#00B870"), 1.2))
            painter.drawEllipse(QPointF(cx, cy), 7, 7)
            painter.setPen(QPen(QColor("#003322"), 1.5))
            painter.drawLine(QPointF(cx - 3, cy), QPointF(cx - 1, cy + 3))
            painter.drawLine(QPointF(cx - 1, cy + 3), QPointF(cx + 3, cy - 3))
            return

        # Pulsing SOS rings
        for ph in (0.0, 0.5):
            p2 = (pulse + ph) % 1.0
            r = 9 + 9 * p2
            a = int(220 * (1 - p2))
            painter.setPen(QPen(QColor(255, 200, 0, a), 1.6))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(cx, cy), r, r)

        # Body (gold disc with darker border)
        if is_target:
            painter.setBrush(QBrush(QColor("#FFD700")))
            painter.setPen(QPen(QColor("#FF8800"), 1.4))
        else:
            painter.setBrush(QBrush(QColor("#FFD700")))
            painter.setPen(QPen(QColor("#B8860B"), 1.0))
        painter.drawEllipse(QPointF(cx, cy), 7, 7)

        # "!" mark
        painter.setPen(QPen(QColor("#1A1A1A")))
        painter.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        painter.drawText(QRectF(cx - 4, cy - 5, 8, 10),
                         Qt.AlignmentFlag.AlignCenter, "!")

        # SOS label
        painter.setPen(QPen(QColor("#FFD700")))
        painter.setFont(QFont("Courier New", 5, QFont.Weight.Bold))
        painter.drawText(QRectF(cx - 14, cy - 18, 28, 8),
                         Qt.AlignmentFlag.AlignCenter, "S.O.S")

    # ============== OVERLAYS ==============
    def _draw_risk_overlay(self, painter, rect, risk, pulse):
        if risk == "High":
            grad = QRadialGradient(rect.center(), rect.width() * 0.7)
            a = int(110 + 40 * pulse)
            grad.setColorAt(0, QColor(255, 30, 50, a))
            grad.setColorAt(0.6, QColor(255, 30, 50, a // 3))
            grad.setColorAt(1, QColor(255, 30, 50, 0))
            painter.fillRect(rect, QBrush(grad))
            painter.setPen(QPen(QColor(255, 80, 80, 200)))
            painter.setFont(QFont("Courier New", 5, QFont.Weight.Bold))
            painter.drawText(rect.adjusted(2, 2, -2, -2),
                             Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight,
                             "◈HI")
        elif risk == "Medium":
            painter.fillRect(rect, QBrush(QColor(255, 180, 0, 50)))
            painter.setPen(QPen(QColor(255, 180, 0, 160)))
            painter.setFont(QFont("Courier New", 5, QFont.Weight.Bold))
            painter.drawText(rect.adjusted(2, 2, -2, -2),
                             Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight,
                             "◈MD")
        elif risk == "Low":
            painter.fillRect(rect, QBrush(QColor(0, 255, 156, 25)))

    def _draw_density_bar(self, painter, rect, density):
        density = max(0.0, min(1.0, density))
        bar_h = max(1.0, rect.height() * 0.10 * density)
        col = QColor(int(255 * density),
                     int(220 * (1 - density)),
                     30, 200)
        painter.fillRect(QRectF(rect.left() + 4, rect.bottom() - bar_h - 3,
                                rect.width() - 8, bar_h),
                         QBrush(col))

    def _draw_coverage_overlay(self, painter, pulse):
        for n in c3_ambulance.get_positions():
            if n not in graph.g.nodes:
                continue
            ctr = self.cell_center(*graph.get_node(n)["grid_pos"])
            cov_r = CELL_SIZE * 3.0
            # multi-ring sonar
            for ring in range(3):
                phase = (pulse + ring * 0.33) % 1.0
                rr = cov_r * phase
                ra = int(120 * (1 - phase))
                painter.setPen(QPen(QColor(0, 180, 255, ra), 1))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(ctr, rr, rr)
            # static dashed boundary
            painter.setPen(QPen(QColor(0, 180, 255, 60), 1.2, Qt.PenStyle.DashLine))
            painter.drawEllipse(ctr, cov_r, cov_r)
            # gradient fill
            cg = QRadialGradient(ctr, cov_r)
            cg.setColorAt(0, QColor(0, 100, 255, 18))
            cg.setColorAt(1, QColor(0, 100, 255, 0))
            painter.setBrush(QBrush(cg))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(ctr, cov_r, cov_r)

    # ============== BOOT SCREEN ==============
    def _draw_boot_sequence(self, painter):
        sr = self.scene_obj.sceneRect()
        cx = sr.width() / 2
        cy = sr.height() / 2

        # Title
        painter.setPen(QPen(QColor(THEME["accent"])))
        painter.setFont(QFont("Courier New", 32, QFont.Weight.Bold))
        painter.drawText(QRectF(0, cy - 80, sr.width(), 50),
                         Qt.AlignmentFlag.AlignCenter, "CITYMIND")
        # Subtitle
        painter.setPen(QPen(QColor(THEME["text_dim"])))
        painter.setFont(QFont("Courier New", 9))
        painter.drawText(QRectF(0, cy - 40, sr.width(), 20),
                         Qt.AlignmentFlag.AlignCenter,
                         "URBAN  ·  INTELLIGENCE  ·  SYSTEM")
        # Loading bar
        bar_w = 320
        bar_h = 4
        bar_x = cx - bar_w / 2
        bar_y = cy + 20
        painter.fillRect(QRectF(bar_x, bar_y, bar_w, bar_h),
                         QBrush(QColor(THEME["panel"])))
        # Animated fill
        fill_w = ((self.pulse / math.tau) % 1.0) * bar_w
        painter.fillRect(QRectF(bar_x, bar_y, fill_w, bar_h),
                         QBrush(QColor(THEME["accent"])))
        # Status messages cycling
        msgs = [
            "LOADING CITY GRAPH...",
            "RUNNING CONSTRAINT SOLVER (CSP)...",
            "BUILDING ROAD NETWORK (GA + MST)...",
            "TRAINING CRIME CLASSIFIER (ML)...",
            "PLACING AMBULANCES (SIMULATED ANNEALING)...",
            "INITIALISING A* ROUTER...",
            "SYSTEM ONLINE",
        ]
        idx = int(self.pulse * 1.3) % len(msgs)
        painter.setPen(QPen(QColor(THEME["text_dim"])))
        painter.setFont(QFont("Courier New", 9))
        painter.drawText(QRectF(bar_x, bar_y + 15, bar_w, 20),
                         Qt.AlignmentFlag.AlignCenter, msgs[idx])

        # Decorative blinking dots
        dot_a = int(120 + 120 * math.sin(self.pulse * 3))
        painter.setBrush(QBrush(QColor(0, 180, 255, dot_a)))
        painter.setPen(Qt.PenStyle.NoPen)
        for i in range(3):
            painter.drawEllipse(QPointF(cx - 30 + i * 30, cy - 10), 3, 3)


# ----------------- Main Window -----------------
class CityMindApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CityMind — Urban Intelligence System")
        self.resize(1320, 840)
        self._apply_stylesheet()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(2)
        self.setCentralWidget(splitter)

        # Column 1: Canvas
        self.canvas = GridCanvas()
        canvas_wrap = QWidget()
        cw = QVBoxLayout(canvas_wrap)
        cw.setContentsMargins(14, 14, 6, 14)
        title_row = QHBoxLayout()
        t = QLabel("CITYMIND")
        t.setObjectName("title")
        title_row.addWidget(t)
        title_row.addStretch()
        sub = QLabel("URBAN  •  INTELLIGENCE  •  SYSTEM")
        sub.setObjectName("subtitle")
        title_row.addWidget(sub)
        cw.addLayout(title_row)
        cw.addWidget(self.canvas, 1)

        self.ctrl_panel = self._build_control_panel()
        self.log_panel = self._build_log_panel()

        splitter.addWidget(canvas_wrap)
        splitter.addWidget(self.ctrl_panel)
        splitter.addWidget(self.log_panel)
        splitter.setSizes([600, 380, 260])
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setStretchFactor(2, 0)
        splitter.setCollapsible(1, False)
        splitter.setCollapsible(2, False)

        sb = QStatusBar()
        sb.setSizeGripEnabled(False)
        self.setStatusBar(sb)
        self.status_lbl = QLabel("Initialising...")
        sb.addPermanentWidget(self.status_lbl)

        self.sim_timer = QTimer(self)
        self.sim_timer.timeout.connect(self._tick)
        self.repaint_timer = QTimer(self)
        self.repaint_timer.timeout.connect(self._repaint)
        self.repaint_timer.start(50)

        self._playing = False
        self._log_count = 0
        self._init_thread = None
        self._current_interval = 700
        self._setup_shortcuts()

        QTimer.singleShot(100, self._do_init)

    def _apply_stylesheet(self):
        self.setStyleSheet(f"""
            * {{ font-family: "Segoe UI", "Tahoma", "Arial", sans-serif; }}
            QMainWindow, QWidget {{
                background: {THEME['bg']}; color: {THEME['text']};
                font-family: "Segoe UI", "Tahoma", "Arial", sans-serif;
                font-size: 12px;
            }}
            QLabel#title {{
                font-size: 26px; font-weight: 800; letter-spacing: 4px;
                color: {THEME['accent']};
            }}
            QLabel#subtitle {{
                color: {THEME['text_dim']}; font-size: 10px;
                letter-spacing: 3px; font-weight: 600;
            }}
            QGroupBox {{
                background: {THEME['panel']};
                border: 1px solid {THEME['border']};
                border-radius: 10px;
                margin-top: 14px;
                padding: 12px 10px 10px 10px;
                font-weight: 600;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 12px; padding: 0 6px;
                color: {THEME['accent']};
                font-size: 10px; letter-spacing: 1.4px; font-weight: 700;
            }}
            QPushButton {{
                background: {THEME['panel_alt']};
                color: {THEME['text']};
                border: 1px solid {THEME['border']};
                border-radius: 6px;
                padding: 0 10px;
                min-height: 30px;
                font-size: 12px;
                font-weight: 700;
                letter-spacing: 1px;
            }}
            QPushButton:hover {{ border: 1px solid {THEME['accent']};
                                 color: {THEME['accent_glow']}; }}
            QPushButton:pressed {{ background: {THEME['accent']}; color: white; }}
            QPushButton#primary {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                  stop:0 {THEME['accent']}, stop:1 {THEME['accent_glow']});
                color: white; border: none;
            }}
            QPushButton#primary:hover {{ background: {THEME['accent_glow']}; }}
            QPushButton#danger {{
                background: {THEME['panel_alt']}; color: {THEME['danger']};
                border: 1px solid {THEME['danger']};
            }}
            QCheckBox {{
                spacing: 10px;
                padding: 5px 2px;
                color: {THEME['text']};
                font-size: 12px;
                min-height: 22px;
            }}
            QCheckBox::indicator {{
                width: 16px; height: 16px; border-radius: 4px;
                border: 1px solid {THEME['border_glow']};
                background: {THEME['panel_alt']};
            }}
            QCheckBox::indicator:checked {{
                background: {THEME['accent']}; border: 1px solid {THEME['accent']};
            }}
            QSlider::groove:horizontal {{
                background: {THEME['panel_alt']};
                height: 6px; border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: {THEME['accent']};
                width: 14px; margin: -5px 0; border-radius: 7px;
            }}
            QSlider::sub-page:horizontal {{ background: {THEME['accent']}; border-radius: 3px; }}
            QListWidget {{
                background: {THEME['panel']};
                border: 1px solid {THEME['border']};
                border-radius: 10px;
                padding: 6px;
                font-family: 'Consolas','Cascadia Code',monospace;
                font-size: 11px;
            }}
            QListWidget::item {{ padding: 5px 6px; border-radius: 4px; }}
            QListWidget::item:hover {{ background: {THEME['panel_alt']}; }}
            QStatusBar {{
                background: {THEME['panel']}; color: {THEME['text_dim']};
                border-top: 1px solid {THEME['border']};
            }}
            QSplitter::handle {{ background: {THEME['border']}; }}
        """)

    def _build_control_panel(self):
        panel = QWidget()
        panel.setMinimumWidth(320)
        panel.setMaximumWidth(460)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 10, 10, 10)
        layout.setSpacing(10)

        # Sim controls
        sim_box = QGroupBox("SIMULATION")
        sim_l = QVBoxLayout(sim_box)
        sim_l.setSpacing(8)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.btn_play = QPushButton("PLAY")
        self.btn_play.setObjectName("primary")
        self.btn_play.clicked.connect(self.toggle_play)
        self.btn_step = QPushButton("STEP")
        self.btn_step.clicked.connect(self.step_once)
        row.addWidget(self.btn_play)
        row.addWidget(self.btn_step)
        sim_l.addLayout(row)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        self.btn_reset = QPushButton("RESET")
        self.btn_reset.clicked.connect(self.reset_sim)
        self.btn_reinit = QPushButton("RE-INIT")
        self.btn_reinit.setObjectName("danger")
        self.btn_reinit.clicked.connect(self.reinit_city)
        row2.addWidget(self.btn_reset)
        row2.addWidget(self.btn_reinit)
        sim_l.addLayout(row2)

        sim_l.addWidget(self._slider_row("Max steps", 5, 100, 30, self._on_max_steps))
        sim_l.addWidget(self._slider_row("Speed", 1, 20, 8, self._on_speed))
        layout.addWidget(sim_box)

        # View controls: zoom slider + fit-to-view button
        view_box = QGroupBox("VIEW")
        view_l = QVBoxLayout(view_box)
        view_l.setSpacing(6)
        view_l.addWidget(self._slider_row(
            "Zoom", 50, 300, 100, self._on_zoom))
        btn_fit = QPushButton("FIT WHOLE MAP")
        btn_fit.clicked.connect(self._on_fit)
        view_l.addWidget(btn_fit)
        layout.addWidget(view_box)

        # Overlays
        ov_box = QGroupBox("OVERLAYS")
        ov_l = QVBoxLayout(ov_box)
        self.cb_roads = self._mk_check("Road Network", "roads", True)
        self.cb_amb = self._mk_check("Ambulance Coverage", "ambulance_coverage", False)
        self.cb_crime = self._mk_check("Crime Heatmap", "crime_heatmap", True)
        self.cb_police = self._mk_check("Police Zones", "police_zones", False)
        self.cb_astar = self._mk_check("A* Path", "astar", True)
        self.cb_density = self._mk_check("Population Density", "density", False)
        for cb in [self.cb_roads, self.cb_amb, self.cb_crime, self.cb_police,
                   self.cb_astar, self.cb_density]:
            ov_l.addWidget(cb)
        layout.addWidget(ov_box)

        # Stats
        stats_box = QGroupBox("STATS")
        stats_l = QVBoxLayout(stats_box)
        self.stat_step = self._stat_line("Step", "0 / 30")
        self.stat_rescued = self._stat_line("Civilians", "0 / 4")
        self.stat_blocked = self._stat_line("Roads blocked", "0")
        self.stat_risk = self._stat_line("Risk H/M/L", "0 / 0 / 0")
        self.stat_police = self._stat_line("Police active", "0")
        self.stat_amb = self._stat_line("Ambulances", "0")
        for w in [self.stat_step, self.stat_rescued, self.stat_blocked,
                  self.stat_risk, self.stat_police, self.stat_amb]:
            stats_l.addLayout(w)
        layout.addWidget(stats_box)

        # Legend
        leg_box = QGroupBox("LEGEND")
        leg_l = QVBoxLayout(leg_box)
        for t, col in CELL_COLORS.items():
            if t == "Empty":
                continue
            row = QHBoxLayout()
            sw = QLabel()
            sw.setFixedSize(14, 14)
            sw.setStyleSheet(f"background: {col}; border-radius: 3px;")
            row.addWidget(sw)
            row.addWidget(QLabel(f"  {t}"))
            row.addStretch()
            leg_l.addLayout(row)
        # Risk legend
        risk_row = QHBoxLayout()
        for label, q in [("HIGH", RISK_BORDER["High"]),
                         ("MED",  RISK_BORDER["Medium"]),
                         ("LOW",  RISK_BORDER["Low"])]:
            chip = QLabel(label)
            chip.setFixedHeight(18)
            chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chip.setStyleSheet(
                f"border: 2px solid rgb({q.red()},{q.green()},{q.blue()}); "
                f"border-radius: 4px; padding: 0 6px; font-size: 9px; "
                f"font-weight: 700; color: rgb({q.red()},{q.green()},{q.blue()});"
            )
            risk_row.addWidget(chip)
        leg_l.addLayout(risk_row)
        layout.addWidget(leg_box)

        layout.addStretch()
        return panel

    def _stat_line(self, label, value):
        row = QHBoxLayout()
        row.setContentsMargins(0, 2, 0, 2)
        l = QLabel(label)
        l.setStyleSheet(f"color: {THEME['text_dim']}; font-size: 12px;")
        l.setMinimumHeight(18)
        v = QLabel(value)
        v.setStyleSheet(f"color: {THEME['text']}; font-weight: 700; font-size: 12px;")
        v.setMinimumHeight(18)
        v.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(l)
        row.addStretch()
        row.addWidget(v)
        # store value label as attribute for updating
        row._value_label = v
        return row

    def _mk_check(self, label, key, default):
        cb = QCheckBox(label)
        cb.setChecked(default)
        cb.toggled.connect(lambda v, k=key: self.canvas.set_overlay(k, v))
        return cb

    def _slider_row(self, label, lo, hi, val, cb):
        wrap = QWidget()
        v = QVBoxLayout(wrap)
        v.setContentsMargins(0, 6, 0, 2)
        v.setSpacing(4)
        lbl = QLabel(f"{label}: {val}")
        lbl.setStyleSheet(f"color: {THEME['text_dim']}; font-size: 11px; "
                          f"font-weight: 600; letter-spacing: 0.5px;")
        lbl.setMinimumHeight(16)
        v.addWidget(lbl)
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(lo, hi); s.setValue(val)
        s.setMinimumHeight(18)
        s.valueChanged.connect(lambda x, l=lbl, name=label: l.setText(f"{name}: {x}"))
        s.valueChanged.connect(cb)
        v.addWidget(s)
        return wrap

    def _on_max_steps(self, v):
        runner.set_max_steps(v)

    def _on_speed(self, v):
        interval = max(80, 1100 - v * 50)
        self._current_interval = interval
        if self._playing:
            self.sim_timer.start(interval)

    def _on_zoom(self, v):
        # Slider value is a percentage (50..300).
        self.canvas.set_zoom(v / 100.0)

    def _on_fit(self):
        self.canvas.fit_map()
        # Keep the zoom slider in sync at 100 %.
        # Walk the VIEW groupbox to find the QSlider and reset it.
        for s in self.ctrl_panel.findChildren(QSlider):
            # Only reset the slider whose current-range matches our zoom row.
            if s.minimum() == 50 and s.maximum() == 300:
                s.blockSignals(True)
                s.setValue(100)
                s.blockSignals(False)
                # Update the label above it (sibling QLabel in same parent).
                parent = s.parentWidget()
                if parent is not None:
                    for lbl in parent.findChildren(QLabel):
                        if lbl.text().startswith("Zoom"):
                            lbl.setText("Zoom: 100")
                break

    def _build_log_panel(self):
        panel = QWidget()
        panel.setMinimumWidth(220)
        panel.setMaximumWidth(360)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 14, 14, 14)
        layout.setSpacing(8)

        title = QLabel("EVENT LOG")
        title.setStyleSheet(f"color: {THEME['accent']}; font-size: 10px; "
                            f"letter-spacing: 2px; font-weight: 700;")
        layout.addWidget(title)
        self.log_list = QListWidget()
        layout.addWidget(self.log_list, 1)
        save_btn = QPushButton("💾  Save log to file")
        save_btn.clicked.connect(self.save_log)
        layout.addWidget(save_btn)
        return panel

    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Space"), self, activated=self.toggle_play)
        QShortcut(QKeySequence("Right"), self, activated=self.step_once)
        QShortcut(QKeySequence("R"), self, activated=lambda: self.cb_roads.toggle())
        QShortcut(QKeySequence("A"), self, activated=lambda: self.cb_amb.toggle())
        QShortcut(QKeySequence("C"), self, activated=lambda: self.cb_crime.toggle())
        QShortcut(QKeySequence("P"), self, activated=lambda: self.cb_police.toggle())
        QShortcut(QKeySequence("F"), self, activated=lambda: self.cb_astar.toggle())
        QShortcut(QKeySequence("D"), self, activated=lambda: self.cb_density.toggle())
        QShortcut(QKeySequence("Ctrl+R"), self, activated=self.reset_sim)
        QShortcut(QKeySequence("Ctrl+I"), self, activated=self.reinit_city)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.save_log)

    # ------------- Actions -------------
    def _do_init(self):
        self.status_lbl.setText("Running CSP / GA / ML pipeline... (≈5–10s)")
        self.btn_play.setEnabled(False); self.btn_step.setEnabled(False)
        self._init_thread = InitThread()
        self._init_thread.finished_ok.connect(self._init_done)
        self._init_thread.failed.connect(self._init_failed)
        self._init_thread.start()

    def _init_done(self):
        self.btn_play.setEnabled(True); self.btn_step.setEnabled(True)
        self.status_lbl.setText("Ready. Press SPACE or Play to start.")
        self.canvas._amb_render = []
        self.canvas._team_trail = []
        self.canvas._last_team = None
        self.canvas.viewport().update()

    def _init_failed(self, msg):
        QMessageBox.critical(self, "Initialization failed", msg)
        self.status_lbl.setText(f"Error: {msg}")

    def toggle_play(self):
        if not runner.is_complete() and not self._playing:
            self._playing = True
            self.btn_play.setText("⏸  PAUSE")
            self.sim_timer.start(self._current_interval)
        else:
            self._playing = False
            self.btn_play.setText("▶  PLAY")
            self.sim_timer.stop()

    def step_once(self):
        if runner.is_complete():
            return
        runner.step()
        if runner.is_complete():
            self._on_complete()

    def _tick(self):
        if runner.is_complete():
            self.toggle_play()
            self._on_complete()
            return
        runner.step()

    def reset_sim(self):
        if self._playing:
            self.toggle_play()
        runner.reset()
        self.canvas._team_trail = []
        self.canvas._last_team = None
        self.status_lbl.setText("Simulation reset.")

    def reinit_city(self):
        if self._playing:
            self.toggle_play()
        self.btn_play.setEnabled(False); self.btn_step.setEnabled(False)
        self.log_list.clear(); self._log_count = 0
        self.status_lbl.setText("Re-initialising city...")
        self._init_thread = InitThread()
        self._init_thread.finished_ok.connect(self._init_done)
        self._init_thread.failed.connect(self._init_failed)
        self._init_thread.start()

    def save_log(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save event log",
                                              "citymind_log.txt", "Text (*.txt)")
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            for e in runner.get_log():
                f.write(f"[{e['timestamp']:%H:%M:%S}] step={e['step']:>3}  "
                        f"{e['type']:<18}  {e['detail']}\n")
        self.status_lbl.setText(f"Log saved to {path}")

    def _on_complete(self):
        s = runner.get_stats()
        msg = (
            f"=== CITYMIND SIMULATION COMPLETE ===\n\n"
            f"Total steps           : {s['step']}\n"
            f"Civilians rescued     : {s['rescued']} / {s['civilians_total']}\n"
            f"Roads blocked         : {s['roads_blocked']}\n"
            f"Roads unblocked       : {s['roads_unblocked']}\n"
            f"Ambulance repositions : {s['ambulance_repositions']}\n"
            f"Police repositions    : {s['police_repositions']}\n"
            f"Crime refreshes       : {s['crime_refreshes']}\n"
            f"A* reroutes           : {s['reroutes']}\n"
            f"Risk distribution     : H:{s['risk']['High']} "
            f"M:{s['risk']['Medium']} L:{s['risk']['Low']}\n"
        )
        print(msg)
        QMessageBox.information(self, "Simulation Complete", msg)

    def _repaint(self):
        self.canvas.viewport().update()
        try:
            s = runner.get_stats()
        except Exception:
            return
        self.stat_step._value_label.setText(f"{s['step']} / {s['max_steps']}")
        self.stat_rescued._value_label.setText(f"{s['rescued']} / {s.get('civilians_total', 4)}")
        self.stat_blocked._value_label.setText(str(s['roads_blocked']))
        self.stat_risk._value_label.setText(
            f"{s['risk']['High']} / {s['risk']['Medium']} / {s['risk']['Low']}")
        self.stat_police._value_label.setText(str(s['police_count']))
        self.stat_amb._value_label.setText(str(len(c3_ambulance.get_positions())))

        log = runner.get_log()
        if len(log) != self._log_count:
            self.log_list.clear()
            for e in reversed(log[-50:]):
                txt = f"[{e['step']:>2}] {e['type']:<14} {e['detail']}"
                item = QListWidgetItem(txt)
                col = EVENT_COLOR.get(e["type"], THEME["text"])
                item.setForeground(QColor(col))
                self.log_list.addItem(item)
            self._log_count = len(log)

    def closeEvent(self, ev):
        try:
            with open("citymind_log.txt", "w", encoding="utf-8") as f:
                for e in runner.get_log():
                    f.write(f"[{e['timestamp']:%H:%M:%S}] step={e['step']:>3}  "
                            f"{e['type']:<18}  {e['detail']}\n")
        except Exception:
            pass
        super().closeEvent(ev)
