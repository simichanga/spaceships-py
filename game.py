import pygame
import os
import math
import random
import sys
from dataclasses import dataclass, field
from typing import List, Tuple

# ----------------- CONFIG -----------------
WIDTH, HEIGHT = 900, 500
FPS, ASSETS = 60, "Assets"
WHITE, BG_COLOR, UI_BG = (255, 255, 255), (7, 10, 20), (20, 24, 30)
RED, YELLOW = (235, 80, 80), (255, 210, 70)
SHIP_W, SHIP_H = 80, 60
BULLET_W, BULLET_H = 10, 5
MAX_BULLETS, METEOR_COUNT = 4, 3
BULLET_SPEED, SHIP_ACCEL, SHIP_DRAG, METEOR_VEL = 850.0, 2400.0, 12.0, 70.0

BORDER = pygame.Rect(WIDTH // 2 - 5, 0, 10, HEIGHT)
YELLOW_HIT, RED_HIT = pygame.USEREVENT + 1, pygame.USEREVENT + 2

# ----------------- UTILS -----------------
def safe_load_image(path, size=None, rotate=0):
    try:
        surf = pygame.image.load(os.path.join(ASSETS, path)).convert_alpha()
        if size: surf = pygame.transform.scale(surf, size)
        if rotate: surf = pygame.transform.rotate(surf, rotate)
        return surf
    except: return None

def safe_load_sound(path):
    try: return pygame.mixer.Sound(os.path.join(ASSETS, path))
    except: return None

# ----------------- ENTITIES -----------------
@dataclass
class Particle:
    pos: pygame.Vector2; vel: pygame.Vector2; color: tuple; life: float; size: float
    def update(self, dt):
        self.pos += self.vel * dt
        self.life -= dt
        self.size = max(0.0, self.size - dt * 10)
    def is_dead(self): return self.life <= 0 or self.size <= 0

class Bullet:
    def __init__(self, pos, speed, owner_name, color):
        self.rect = pygame.Rect(pos[0], pos[1], BULLET_W, BULLET_H)
        self.vel_x, self.owner, self.color = speed, owner_name, color
        self.trail, self.life = [], 2.0

    def update(self, dt):
        self.rect.x += int(self.vel_x * dt)
        self.life -= dt
        self.trail.append(self.rect.center)
        if len(self.trail) > 7: self.trail.pop(0)

class Ship:
    def __init__(self, x, y, color, controls, shoot_key, img, bullet_speed):
        self.pos = pygame.Vector2(x, y)
        self.vel = pygame.Vector2(0, 0)
        self.color, self.controls, self.shoot_key = color, controls, shoot_key
        self.img, self.bullet_speed = img, bullet_speed
        self.health = 10.0
        self.display_health = 10.0

    def get_rect(self): return pygame.Rect(int(self.pos.x), int(self.pos.y), SHIP_W, SHIP_H)

    def update(self, dt, area):
        keys = pygame.key.get_pressed()
        acc = pygame.Vector2(0, 0)
        if keys[self.controls[0]]: acc.y -= 1 # Up
        if keys[self.controls[1]]: acc.y += 1 # Down
        if keys[self.controls[2]]: acc.x -= 1 # Left
        if keys[self.controls[3]]: acc.x += 1 # Right
        
        if acc.length_squared() > 0: self.vel += acc.normalize() * SHIP_ACCEL * dt
        self.vel -= self.vel * min(1.0, SHIP_DRAG * dt)
        self.pos += self.vel * dt
        
        # Constrain to area
        self.pos.x = max(area.left, min(area.right - SHIP_W, self.pos.x))
        self.pos.y = max(area.top, min(area.bottom - SHIP_H, self.pos.y))
        self.display_health += (self.health - self.display_health) * dt * 6

@dataclass
class Meteor:
    rect: pygame.Rect; vx: float; vy: float; angle: float = 0.0; rot_speed: float = 0.0
    def update(self, dt):
        self.rect.x += int(self.vx * dt)
        self.rect.y += int(self.vy * dt)
        self.angle = (self.angle + self.rot_speed * dt) % 360
        if self.rect.left > WIDTH: self.rect.right = 0
        elif self.rect.right < 0: self.rect.left = WIDTH
        if self.rect.top > HEIGHT: self.rect.bottom = 0
        elif self.rect.bottom < 0: self.rect.top = HEIGHT

class ScreenShake:
    def __init__(self): self.timer, self.magnitude = 0, 0
    def trigger(self, mag=10, dur=0.3): self.timer, self.magnitude = dur, mag
    def get_offset(self, dt):
        if self.timer > 0:
            self.timer -= dt
            return (random.randint(-1, 1) * self.magnitude, random.randint(-1, 1) * self.magnitude)
        return (0, 0)

# ----------------- MAIN GAME -----------------
class SpaceFight:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("arial", 18); self.font_big = pygame.font.SysFont("arial", 84)
        
        # Assets
        self.bg = safe_load_image("space.png", (WIDTH, HEIGHT))
        self.meteor_img = safe_load_image("meteor.png", (50, 50))
        self.snd_laser, self.snd_hit = safe_load_sound("laser.wav"), safe_load_sound("explosion.wav")

        # Players
        y_ctrls = (pygame.K_w, pygame.K_s, pygame.K_a, pygame.K_d)
        r_ctrls = (pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT)
        
        self.yellow = Ship(100, 220, YELLOW, y_ctrls, pygame.K_LCTRL, 
                           safe_load_image("spaceship_yellow.png", (SHIP_W, SHIP_H), 90), BULLET_SPEED)
        self.red = Ship(720, 220, RED, r_ctrls, pygame.K_RCTRL, 
                        safe_load_image("spaceship_red.png", (SHIP_W, SHIP_H), 270), -BULLET_SPEED)
        
        self.ships = [self.yellow, self.red]
        self.bullets, self.meteors, self.particles = [], [], []
        self.shake, self.hit_flash, self.bg_off = ScreenShake(), 0.0, 0.0
        for _ in range(METEOR_COUNT): self._spawn_meteor()

    def _spawn_meteor(self):
        vx, vy = random.choice([-1, 1]) * METEOR_VEL, random.choice([-1, 1]) * METEOR_VEL
        self.meteors.append(Meteor(pygame.Rect(WIDTH//2, random.randint(0, HEIGHT), 50, 50), vx, vy, 0, random.uniform(-90, 90)))

    def _spawn_particles(self, pos, color, count=15):
        for _ in range(count):
            vel = pygame.Vector2(random.uniform(-1, 1), random.uniform(-1, 1)).normalize() * random.uniform(50, 200)
            self.particles.append(Particle(pygame.Vector2(pos), vel, color, random.uniform(0.4, 0.8), random.uniform(2, 5)))

    def handle_fire(self, ship):
        if sum(1 for b in self.bullets if b.owner == ship) < MAX_BULLETS:
            start_x = ship.get_rect().right if ship.bullet_speed > 0 else ship.get_rect().left
            self.bullets.append(Bullet((start_x, ship.get_rect().centery), ship.bullet_speed, ship, ship.color))
            if self.snd_laser: self.snd_laser.play()

    def update(self, dt):
        self.hit_flash = max(0.0, self.hit_flash - dt * 3)
        self.bg_off = (self.bg_off + dt * 20) % WIDTH
        
        # Ship areas
        self.yellow.update(dt, pygame.Rect(0, 0, BORDER.left, HEIGHT))
        self.red.update(dt, pygame.Rect(BORDER.right, 0, WIDTH - BORDER.right, HEIGHT))

        for m in self.meteors: m.update(dt)
        for p in self.particles[:]:
            p.update(dt)
            if p.is_dead(): self.particles.remove(p)

        for b in self.bullets[:]:
            b.update(dt)
            if b.life <= 0 or not self.screen.get_rect().contains(b.rect):
                self.bullets.remove(b); continue
            
            # Bullet Collisions
            for s in self.ships:
                if s != b.owner and s.get_rect().colliderect(b.rect):
                    s.health -= 1
                    self.shake.trigger()
                    self.hit_flash = 0.5
                    self._spawn_particles(b.rect.center, s.color, 20)
                    if self.snd_hit: self.snd_hit.play()
                    self.bullets.remove(b)
                    break

    def draw(self, offset):
        self.screen.fill(BG_COLOR)
        if self.bg:
            self.screen.blit(self.bg, (-self.bg_off + offset[0], offset[1]))
            self.screen.blit(self.bg, (WIDTH - self.bg_off + offset[0], offset[1]))
        
        pygame.draw.rect(self.screen, (15, 15, 25), BORDER)
        
        for b in self.bullets:
            for i, pt in enumerate(b.trail):
                alpha = int(255 * (i/len(b.trail)))
                pygame.draw.circle(self.screen, (*b.color, alpha), pt, 2)
            pygame.draw.rect(self.screen, b.color, b.rect)

        for s in self.ships:
            if s.img: self.screen.blit(s.img, s.get_rect().topleft)
            else: pygame.draw.rect(self.screen, s.color, s.get_rect())
            # Health Bar
            bar_x = 10 if s == self.yellow else WIDTH - 230
            pygame.draw.rect(self.screen, UI_BG, (bar_x, 10, 220, 15))
            pygame.draw.rect(self.screen, s.color, (bar_x+2, 12, int(216 * (s.display_health/10)), 11))

        for m in self.meteors:
            if self.meteor_img:
                rot = pygame.transform.rotate(self.meteor_img, m.angle)
                self.screen.blit(rot, rot.get_rect(center=m.rect.center).topleft)

        for p in self.particles:
            pygame.draw.circle(self.screen, p.color, (int(p.pos.x), int(p.pos.y)), int(p.size))

        if self.hit_flash > 0:
            s = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            s.fill((255, 255, 255, int(self.hit_flash * 100)))
            self.screen.blit(s, (0, 0))

        pygame.display.flip()

    def run(self):
        while True:
            dt = self.clock.tick(FPS) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT: return
                if event.type == pygame.KEYDOWN:
                    if event.key == self.yellow.shoot_key: self.handle_fire(self.yellow)
                    if event.key == self.red.shoot_key: self.handle_fire(self.red)

            self.update(dt)
            self.draw(self.shake.get_offset(dt))
            
            if self.yellow.health <= 0 or self.red.health <= 0:
                pygame.time.delay(1000); break
        pygame.quit()

if __name__ == "__main__":
    SpaceFight().run()