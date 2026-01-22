"""
Space Fight — Polished Feel & Look
Copy-paste and run. Place images/sounds in ./Assets if you have them,
but code will run with placeholders if assets are missing.
"""

import pygame
import os
import math
import random
import sys
from dataclasses import dataclass, field
from typing import List, Tuple

# ----------------- CONFIG -----------------
ASSETS = "Assets"
WIDTH, HEIGHT = 900, 500
FPS = 60

WHITE = (255, 255, 255)
BG_COLOR = (7, 10, 20)
RED = (235, 80, 80)
YELLOW = (255, 210, 70)
UI_BG = (20, 24, 30)

SHIP_W, SHIP_H = 80, 60
BULLET_W, BULLET_H = 10, 5
MAX_BULLETS = 4

BULLET_SPEED = 850.0  # pixels/sec
SHIP_ACCEL = 2400.0    # px/s^2
SHIP_DRAG = 12.0       # damping
METEOR_VEL = 70.0      # px/s
METEOR_COUNT = 3

BORDER = pygame.Rect(WIDTH // 2 - 5, 0, 10, HEIGHT)
YELLOW_HIT = pygame.USEREVENT + 1
RED_HIT = pygame.USEREVENT + 2

# particle limits
MAX_PARTICLES = 400

# utility
def asset_path(*parts):
    return os.path.join(ASSETS, *parts)

def safe_load_image(path, size=None, rotate=0):
    try:
        surf = pygame.image.load(path).convert_alpha()
        if size:
            surf = pygame.transform.scale(surf, size)
        if rotate:
            surf = pygame.transform.rotate(surf, rotate)
        return surf
    except Exception:
        return None

def safe_load_sound(path):
    try:
        return pygame.mixer.Sound(path)
    except Exception:
        return None

def lerp(a, b, t):
    return a + (b - a) * max(0, min(1, t))

# --------------- ENTITIES ----------------
@dataclass
class Bullet:
    rect: pygame.Rect
    vel_x: float
    owner: str
    trail: List[Tuple[int,int]] = field(default_factory=list)
    life: float = 2.0  # seconds

    def update(self, dt):
        # dt in seconds
        self.rect.x += int(self.vel_x * dt)
        self.life -= dt
        self.trail.append(self.rect.center)
        if len(self.trail) > 7:
            self.trail.pop(0)

    def is_dead(self):
        return self.life <= 0 or self.rect.right < 0 or self.rect.left > WIDTH

@dataclass
class Meteor:
    rect: pygame.Rect
    vx: float
    vy: float
    angle: float = 0.0
    rot_speed: float = 0.0

    def update(self, dt):
        self.rect.x += int(self.vx * dt)
        self.rect.y += int(self.vy * dt)
        self.angle = (self.angle + self.rot_speed * dt) % 360
        # wrap
        if self.rect.left > WIDTH:
            self.rect.right = 0
        if self.rect.right < 0:
            self.rect.left = WIDTH
        if self.rect.top > HEIGHT:
            self.rect.bottom = 0
        if self.rect.bottom < 0:
            self.rect.top = HEIGHT

@dataclass
class Particle:
    pos: pygame.Vector2
    vel: pygame.Vector2
    color: Tuple[int,int,int]
    life: float
    size: float
    fade: bool = True

    def update(self, dt):
        self.pos += self.vel * dt
        self.life -= dt
        if self.fade:
            self.size = max(0.0, self.size - dt * 10)

    def is_dead(self):
        return self.life <= 0 or self.size <= 0

# ----------------- Screen Shake -----------------
class ScreenShake:
    def __init__(self):
        self.timer = 0.0
        self.magnitude = 0.0
        self.dir = pygame.Vector2(0,0)

    def trigger(self, magnitude=10.0, duration=0.35, direction=None):
        self.timer = duration
        self.magnitude = magnitude
        if direction:
            self.dir = pygame.Vector2(direction).normalize()
        else:
            self.dir = pygame.Vector2(random.uniform(-1,1), random.uniform(-1,1)).normalize()

    def update(self, dt):
        if self.timer > 0:
            self.timer -= dt
            # amplitude decays
            pct = max(0.0, self.timer / (self.timer + 1e-6))
            amp = self.magnitude * pct
            # biased toward provided direction but with randomness
            rx = (random.random() - 0.5) * 2
            ry = (random.random() - 0.5) * 2
            shake = pygame.Vector2(rx, ry) * amp * 0.6 + self.dir * amp * 0.4
            return int(shake.x), int(shake.y)
        return 0, 0

# ----------------- GAME --------------------
class SpaceFight:
    def __init__(self):
        pygame.init()
        try:
            pygame.mixer.init()
        except Exception:
            pass

        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("Space Fight — Polished")
        self.clock = pygame.time.Clock()
        self.font_small = pygame.font.SysFont("arial", 18)
        self.font_big = pygame.font.SysFont("arial", 84)

        # load assets (if available)
        self.bg = safe_load_image(asset_path("space.png"), (WIDTH, HEIGHT))
        self.yellow_img = safe_load_image(asset_path("spaceship_yellow.png"), (SHIP_W, SHIP_H), rotate=90)
        self.red_img = safe_load_image(asset_path("spaceship_red.png"), (SHIP_W, SHIP_H), rotate=270)
        self.meteor_img = safe_load_image(asset_path("meteor.png"), (METEOR_VEL and 50, 50))
        self.laser_snd = safe_load_sound(asset_path("laser.wav"))
        self.hit_snd = safe_load_sound(asset_path("explosion.wav"))

        # ships (pos stored as floats for smooth movement)
        self.yellow_pos = pygame.Vector2(120.0, HEIGHT/2)
        self.red_pos = pygame.Vector2(760.0, HEIGHT/2)
        self.yellow_vel = pygame.Vector2(0,0)
        self.red_vel = pygame.Vector2(0,0)

        self.yellow_health = 10
        self.red_health = 10
        self.max_health = 10

        self.yellow_health_display = float(self.yellow_health)
        self.red_health_display = float(self.red_health)

        self.bullets: List[Bullet] = []
        self.meteors: List[Meteor] = []
        self.particles: List[Particle] = []

        # populate meteors
        for _ in range(METEOR_COUNT):
            self._spawn_meteor(center=True)

        self.shake = ScreenShake()
        self.bg_offset = 0.0
        self.hit_flash = 0.0  # white flash on hit
        self.running = True

    # ---------------- helpers ----------------
    def _spawn_meteor(self, center=False):
        if center:
            x = WIDTH//2 + random.randint(-40,40)
            y = HEIGHT//2 + random.randint(-40,40)
        else:
            x = random.randint(0, WIDTH)
            y = random.randint(0, HEIGHT)
        angle = math.radians(random.uniform(0,360))
        vx = math.cos(angle) * METEOR_VEL
        vy = math.sin(angle) * METEOR_VEL
        rot = random.uniform(-90, 90)
        rect = pygame.Rect(int(x), int(y), 50, 50)
        self.meteors.append(Meteor(rect, vx, vy, angle=0.0, rot_speed=rot))

    def _play_sound(self, snd):
        if snd:
            try:
                snd.play()
            except Exception:
                pass

    def _spawn_particles(self, pos, count=20, color=(255,200,50), spread=120.0, speed=140.0, life=0.6, size=4.5):
        for _ in range(count):
            if len(self.particles) > MAX_PARTICLES:
                break
            ang = math.radians(random.uniform(0, 360))
            vel = pygame.Vector2(math.cos(ang), math.sin(ang)) * (random.uniform(0.2,1.0) * speed)
            p = Particle(pygame.Vector2(pos), vel, color, random.uniform(life*0.6, life*1.2), random.uniform(size*0.6, size*1.3))
            self.particles.append(p)

    # --------------- input/fire -------------
    def handle_fire(self, key):
        ship_half_h = SHIP_H // 2

        # YELLOW shoots RIGHT
        if key == pygame.K_LCTRL and self._count_owner_bullets("yellow") < MAX_BULLETS:
            brect = pygame.Rect(
                int(self.yellow_pos.x + SHIP_W // 2),
                int(self.yellow_pos.y + ship_half_h - BULLET_H // 2),
                BULLET_W,
                BULLET_H
            )

            self.bullets.append(Bullet(brect, BULLET_SPEED, "yellow"))
            self._play_sound(self.laser_snd)
            self._spawn_particles(brect.center, count=6, color=YELLOW,
                                speed=220, life=0.18, size=3)

        # RED shoots LEFT
        if key == pygame.K_RCTRL and self._count_owner_bullets("red") < MAX_BULLETS:
            brect = pygame.Rect(
                int(self.red_pos.x - SHIP_W // 2 - BULLET_W),
                int(self.red_pos.y + ship_half_h - BULLET_H // 2),
                BULLET_W,
                BULLET_H
            )

            self.bullets.append(Bullet(brect, -BULLET_SPEED, "red"))
            self._play_sound(self.laser_snd)
            self._spawn_particles(brect.center, count=6, color=RED,
                                speed=220, life=0.18, size=3)


    def _count_owner_bullets(self, owner):
        return sum(1 for b in self.bullets if b.owner == owner)

    # -------------- updates ----------------
    def update(self, dt):
        # dt seconds
        # ---------------- ships movement: acceleration + drag for "weight" ------------
        keys = pygame.key.get_pressed()
        # yellow control (WASD)
        target_acc = pygame.Vector2(0,0)
        if keys[pygame.K_a]:
            target_acc.x = -1
        if keys[pygame.K_d]:
            target_acc.x = 1
        if keys[pygame.K_w]:
            target_acc.y = -1
        if keys[pygame.K_s]:
            target_acc.y = 1
        if target_acc.length_squared() > 0:
            target_acc = target_acc.normalize() * SHIP_ACCEL
        # apply
        self.yellow_vel += target_acc * dt
        # drag
        self.yellow_vel -= self.yellow_vel * min(1.0, SHIP_DRAG * dt)
        # integrate
        self.yellow_pos += self.yellow_vel * dt
        # clamp left area
        left_area = pygame.Rect(0,0,BORDER.left, HEIGHT)
        if self.yellow_pos.x < left_area.left: self.yellow_pos.x = left_area.left
        if self.yellow_pos.x + SHIP_W > left_area.right: self.yellow_pos.x = left_area.right - SHIP_W
        self.yellow_pos.y = max(0, min(HEIGHT - SHIP_H, self.yellow_pos.y))

        # red control (arrows)
        targ_acc = pygame.Vector2(0,0)
        if keys[pygame.K_LEFT]:
            targ_acc.x = -1
        if keys[pygame.K_RIGHT]:
            targ_acc.x = 1
        if keys[pygame.K_UP]:
            targ_acc.y = -1
        if keys[pygame.K_DOWN]:
            targ_acc.y = 1
        if targ_acc.length_squared() > 0:
            targ_acc = targ_acc.normalize() * SHIP_ACCEL
        self.red_vel += targ_acc * dt
        self.red_vel -= self.red_vel * min(1.0, SHIP_DRAG * dt)
        self.red_pos += self.red_vel * dt
        # clamp right area
        right_area = pygame.Rect(BORDER.right, 0, WIDTH - BORDER.right, HEIGHT)
        if self.red_pos.x < right_area.left: self.red_pos.x = right_area.left
        if self.red_pos.x + SHIP_W > right_area.right: self.red_pos.x = right_area.right - SHIP_W
        self.red_pos.y = max(0, min(HEIGHT - SHIP_H, self.red_pos.y))

        # ---------------- bullets ----------------
        for b in self.bullets[:]:
            b.update(dt)
            # check collisions with meteors
            hit_meteor = None
            for m in self.meteors:
                if m.rect.colliderect(b.rect):
                    hit_meteor = m
                    break
            if hit_meteor:
                # spawn particles at impact, reset meteor
                self._spawn_particles(b.rect.center, count=18, color=(200,200,200), speed=160, life=0.7, size=3.8)
                # respawn meteor somewhere else
                hit_meteor.rect.x = random.randint(50, WIDTH-50)
                hit_meteor.rect.y = random.randint(50, HEIGHT-50)
                hit_meteor.vx = math.cos(random.random()*6.28) * METEOR_VEL
                hit_meteor.vy = math.sin(random.random()*6.28) * METEOR_VEL
                try:
                    self.bullets.remove(b)
                except ValueError:
                    pass
                continue
            # check hit ship
            if b.owner == "yellow" and self._ship_rect(self.red_pos).colliderect(b.rect):
                pygame.event.post(pygame.event.Event(RED_HIT))
                try:
                    self.bullets.remove(b)
                except ValueError:
                    pass
                continue
            if b.owner == "red" and self._ship_rect(self.yellow_pos).colliderect(b.rect):
                pygame.event.post(pygame.event.Event(YELLOW_HIT))
                try:
                    self.bullets.remove(b)
                except ValueError:
                    pass
                continue
            # lifetime/out of bounds
            if b.is_dead():
                try:
                    self.bullets.remove(b)
                except ValueError:
                    pass

        # ---------------- meteors ----------------
        for m in self.meteors:
            m.update(dt)
            # collision with ships
            if m.rect.colliderect(self._ship_rect(self.yellow_pos)):
                pygame.event.post(pygame.event.Event(YELLOW_HIT))
                # small explosion
                self._spawn_particles(m.rect.center, count=14, color=(220,120,80), speed=120, life=0.6)
                # respawn meteor
                m.rect.x = random.randint(40, WIDTH-40)
                m.rect.y = random.randint(40, HEIGHT-40)
            if m.rect.colliderect(self._ship_rect(self.red_pos)):
                pygame.event.post(pygame.event.Event(RED_HIT))
                self._spawn_particles(m.rect.center, count=14, color=(220,120,80), speed=120, life=0.6)
                m.rect.x = random.randint(40, WIDTH-40)
                m.rect.y = random.randint(40, HEIGHT-40)

        # ---------------- particles ---------------
        for p in self.particles[:]:
            p.update(dt)
            if p.is_dead():
                try:
                    self.particles.remove(p)
                except ValueError:
                    pass

        # ---------------- screen shake & hit flash -----------
        # handled in draw/update of shakes
        if self.hit_flash > 0:
            self.hit_flash = max(0.0, self.hit_flash - dt*2.5)

        # HUD health smoothing (lerp)
        self.yellow_health_display = lerp(self.yellow_health_display, float(self.yellow_health), min(1.0, dt*6.0))
        self.red_health_display = lerp(self.red_health_display, float(self.red_health), min(1.0, dt*6.0))

    def _ship_rect(self, posvec):
        return pygame.Rect(int(posvec.x), int(posvec.y), SHIP_W, SHIP_H)

    # ----------------- drawing -----------------
    def draw_glow_rect(self, surf, rect, color):
        # quick soft glow using alpha surface
        glow = pygame.Surface((rect.width*3, rect.height*3), pygame.SRCALPHA)
        inner = glow.get_rect().inflate(-rect.width, -rect.height)
        pygame.draw.ellipse(glow, (*color, 70), inner)
        surf.blit(glow, (rect.x - rect.width, rect.y - rect.height), special_flags=pygame.BLEND_PREMULTIPLIED)
        pygame.draw.rect(surf, color, rect, border_radius=3)

    def draw(self, dt):
        # shake offset
        sx, sy = self.shake.update(dt)
        # parallax bg
        self.bg_offset = (self.bg_offset + dt * 20.0) % WIDTH
        if self.bg:
            self.screen.blit(self.bg, (-self.bg_offset + sx, sy))
            self.screen.blit(self.bg, (WIDTH - self.bg_offset + sx, sy))
        else:
            self.screen.fill(BG_COLOR)

        # center border
        pygame.draw.rect(self.screen, (18,20,24), BORDER)

        # meteors (rotating)
        for m in self.meteors:
            if self.meteor_img:
                rot = pygame.transform.rotate(self.meteor_img, m.angle)
                r = rot.get_rect(center=m.rect.center)
                self.screen.blit(rot, r.topleft)
            else:
                pygame.draw.ellipse(self.screen, (120,120,130), m.rect)

        # bullets trails then bullets
        for b in self.bullets:
            # draw trail
            if b.trail:
                points = b.trail[:]
                for i, pt in enumerate(points):
                    alpha = int(200 * (i / max(1, len(points)-1)))
                    size = 2 + i*0.6
                    s = pygame.Surface((int(size*2), int(size*2)), pygame.SRCALPHA)
                    color = YELLOW if b.owner == "yellow" else RED
                    pygame.draw.circle(s, (*color, alpha), (int(size), int(size)), int(size))
                    self.screen.blit(s, (pt[0]-size, pt[1]-size))
            # glowing bullet
            self.draw_glow_rect(self.screen, b.rect, YELLOW if b.owner == "yellow" else RED)

        # ships (draw sprites or boxes)
        yrect = self._ship_rect(self.yellow_pos)
        rrect = self._ship_rect(self.red_pos)
        if self.yellow_img:
            self.screen.blit(self.yellow_img, yrect.topleft)
        else:
            pygame.draw.rect(self.screen, YELLOW, yrect, border_radius=6)
        if self.red_img:
            self.screen.blit(self.red_img, rrect.topleft)
        else:
            pygame.draw.rect(self.screen, RED, rrect, border_radius=6)

        # particles (draw simple circles)
        for p in self.particles:
            s = pygame.Surface((int(p.size*2), int(p.size*2)), pygame.SRCALPHA)
            # fade with life
            alpha = int(255 * max(0.0, min(1.0, p.life / 1.0)))
            pygame.draw.circle(s, (*p.color, alpha), (int(p.size), int(p.size)), int(max(1, p.size)))
            self.screen.blit(s, (p.pos.x - p.size + sx, p.pos.y - p.size + sy))

        # UI: health bars with smoothed display
        # background bar
        bar_w, bar_h = 220, 18
        # left - yellow
        pygame.draw.rect(self.screen, UI_BG, (10, 10, bar_w, bar_h), border_radius=6)
        inner_w = int((self.yellow_health_display / self.max_health) * (bar_w-4))
        pygame.draw.rect(self.screen, YELLOW, (12, 12, inner_w, bar_h-4), border_radius=6)
        pygame.draw.rect(self.screen, WHITE, (10, 10, bar_w, bar_h), 2, border_radius=6)
        # right - red
        pygame.draw.rect(self.screen, UI_BG, (WIDTH - bar_w - 10, 10, bar_w, bar_h), border_radius=6)
        inner_w2 = int((self.red_health_display / self.max_health) * (bar_w-4))
        pygame.draw.rect(self.screen, RED, (WIDTH - bar_w - 8, 12, inner_w2, bar_h-4), border_radius=6)
        pygame.draw.rect(self.screen, WHITE, (WIDTH - bar_w - 10, 10, bar_w, bar_h), 2, border_radius=6)

        # small labels
        ytxt = self.font_small.render(f"Yellow: {int(self.yellow_health)}", True, WHITE)
        rtxt = self.font_small.render(f"Red: {int(self.red_health)}", True, WHITE)
        self.screen.blit(ytxt, (12, 12 + bar_h + 6))
        self.screen.blit(rtxt, (WIDTH - bar_w - 10 + 6, 12 + bar_h + 6))

        # hit flash overlay
        if self.hit_flash > 0:
            s = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            alpha = int(150 * self.hit_flash)
            s.fill((255,255,255, alpha))
            self.screen.blit(s, (0,0))

        # winner check text
        if self.yellow_health <= 0 or self.red_health <= 0:
            winner = "Red Wins!" if self.yellow_health <= 0 else "Yellow Wins!"
            surf = self.font_big.render(winner, True, WHITE)
            r = surf.get_rect(center=(WIDTH//2 + sx, HEIGHT//2 + sy))
            self.screen.blit(surf, r.topleft)

        pygame.display.flip()

    # ---------------- main loop ---------------
    def run(self):
        # main loop
        while self.running:
            dt_ms = self.clock.tick(FPS)
            dt = dt_ms / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                if event.type == pygame.KEYDOWN:
                    self.handle_fire(event.key)
                if event.type == RED_HIT:
                    self.red_health = max(0, self.red_health - 1)
                    self.shake.trigger(magnitude=10.0, duration=0.35, direction=(-1,0))
                    self._spawn_particles(self._ship_rect(self.red_pos).center, count=22, color=(240,80,80), speed=210, life=0.8, size=5)
                    self._play_sound(self.hit_snd)
                    self.hit_flash = 0.9
                if event.type == YELLOW_HIT:
                    self.yellow_health = max(0, self.yellow_health - 1)
                    self.shake.trigger(magnitude=10.0, duration=0.35, direction=(1,0))
                    self._spawn_particles(self._ship_rect(self.yellow_pos).center, count=22, color=(255,220,70), speed=210, life=0.8, size=5)
                    self._play_sound(self.hit_snd)
                    self.hit_flash = 0.9

            # early exit on winner (show final frame then stop loop)
            if self.red_health <= 0 or self.yellow_health <= 0:
                # show final frame for a short while then exit
                self.draw(dt)
                pygame.time.delay(1800)
                break

            self.update(dt)
            self.draw(dt)

        pygame.quit()

# ----------------- Run --------------------
if __name__ == "__main__":
    Game = SpaceFight()
    Game.run()
