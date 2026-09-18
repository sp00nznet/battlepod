/* Flat-shaded, z-buffered triangles at the pod's own 480x360.
 *
 * `tools/render.py` ported to C so the picture can be made inside the
 * emulator's process. Same camera, same shading, same sky and ground and hard
 * cast shadow that the period footage shows - and the same 480x360 the display
 * list says the pod ran.
 */
#ifndef BATTLEPOD_RASTER_H
#define BATTLEPOD_RASTER_H

#include <math.h>
#include <stdint.h>
#include <string.h>

#include "mesh.h"

#define RAS_W 480
#define RAS_H 360

struct raster {
	uint8_t px[RAS_W * RAS_H * 3];
	float z[RAS_W * RAS_H];
};

/* The palette the footage shows: a graded sky, sand, and a hard dark shadow. */
static const uint8_t RAS_SKY_TOP[3] = { 0x2E, 0x5C, 0xA8 };
static const uint8_t RAS_SKY_LOW[3] = { 0xBF, 0xCF, 0xE2 };
static const uint8_t RAS_GROUND[3]  = { 0xC9, 0xA9, 0x6E };
static const uint8_t RAS_SHADOW[3]  = { 0x6B, 0x55, 0x36 };
static const float RAS_LIGHT[3] = { -0.35f, 0.80f, -0.49f };

static void ras_background(struct raster *f, int horizon)
{
	int y, x, i;

	for (y = 0; y < RAS_H; y++) {
		uint8_t c[3];
		if (y < horizon) {
			float t = (float)y / (horizon > 0 ? horizon : 1);
			for (i = 0; i < 3; i++)
				c[i] = (uint8_t)(RAS_SKY_TOP[i] + (RAS_SKY_LOW[i] - RAS_SKY_TOP[i]) * t);
		} else {
			/* the ground fades toward the horizon - distance haze */
			float t = (float)(y - horizon) / (RAS_H - horizon > 0 ? RAS_H - horizon : 1);
			if (t * 3.0f < 1.0f) t = t * 3.0f; else t = 1.0f;
			for (i = 0; i < 3; i++)
				c[i] = (uint8_t)(RAS_SKY_LOW[i] + (RAS_GROUND[i] - RAS_SKY_LOW[i]) * t);
		}
		for (x = 0; x < RAS_W; x++)
			memcpy(&f->px[(y * RAS_W + x) * 3], c, 3);
	}
	for (i = 0; i < RAS_W * RAS_H; i++) f->z[i] = 1e30f;
}

static void ras_triangle(struct raster *f, const float *p0, const float *p1,
			 const float *p2, const uint8_t *c)
{
	float area;
	int lo_x, hi_x, lo_y, hi_y, x, y;

	lo_x = (int)floorf(fminf(p0[0], fminf(p1[0], p2[0])));
	hi_x = (int)ceilf(fmaxf(p0[0], fmaxf(p1[0], p2[0])));
	lo_y = (int)floorf(fminf(p0[1], fminf(p1[1], p2[1])));
	hi_y = (int)ceilf(fmaxf(p0[1], fmaxf(p1[1], p2[1])));
	if (lo_x < 0) lo_x = 0;
	if (lo_y < 0) lo_y = 0;
	if (hi_x > RAS_W - 1) hi_x = RAS_W - 1;
	if (hi_y > RAS_H - 1) hi_y = RAS_H - 1;
	if (lo_x > hi_x || lo_y > hi_y) return;

	area = (p1[0] - p0[0]) * (p2[1] - p0[1]) - (p2[0] - p0[0]) * (p1[1] - p0[1]);
	if (fabsf(area) < 1e-9f) return;

	for (y = lo_y; y <= hi_y; y++) {
		for (x = lo_x; x <= hi_x; x++) {
			float px = x + 0.5f, py = y + 0.5f, w0, w1, z;
			int i;

			w0 = ((p1[0] - p0[0]) * (py - p0[1]) - (px - p0[0]) * (p1[1] - p0[1])) / area;
			w1 = ((px - p0[0]) * (p2[1] - p0[1]) - (p2[0] - p0[0]) * (py - p0[1])) / area;
			if (w0 < 0 || w1 < 0 || w0 + w1 > 1) continue;
			z = p0[2] + w1 * (p1[2] - p0[2]) + w0 * (p2[2] - p0[2]);
			i = y * RAS_W + x;
			if (z < f->z[i]) {
				f->z[i] = z;
				memcpy(&f->px[i * 3], c, 3);
			}
		}
	}
}

/* One flat colour per face - lit, unless the material is kind 0, which the
 * archive settles as emissive: every light and marker in it points at a kind 0
 * and not one points at a kind 1. */
static void ras_shade(uint8_t *out, float r, float g, float b, const float *nrm, int kind)
{
	float k = 1.0f, c[3];
	int i;

	if (kind != 0) {
		float d = nrm[0] * RAS_LIGHT[0] + nrm[1] * RAS_LIGHT[1] + nrm[2] * RAS_LIGHT[2];
		if (d < 0) d = 0;
		k = 0.35f + 0.65f * d;
	}
	c[0] = r; c[1] = g; c[2] = b;
	for (i = 0; i < 3; i++) {
		float v = 255.0f * c[i] * k;
		out[i] = (uint8_t)(v < 0 ? 0 : (v > 255 ? 255 : v));
	}
}

struct ras_cam {
	float turn, pitch, dist;
	float centre[3];
};

static void ras_view(const struct ras_cam *cam, float x, float y, float z, float *o)
{
	float ct = cosf(cam->turn), st = sinf(cam->turn);
	float cp = cosf(cam->pitch), sp = sinf(cam->pitch);
	float nx, ny, nz;

	x -= cam->centre[0]; y -= cam->centre[1]; z -= cam->centre[2];
	nx = x * ct + z * st;
	nz = -x * st + z * ct;
	ny = y * cp - nz * sp;
	nz = y * sp + nz * cp;
	o[0] = nx; o[1] = ny; o[2] = nz + cam->dist;
}

/* Perspective. Y is up in the model and down on the screen. */
static int ras_project(const float *p, float *o)
{
	float f;

	if (p[2] <= 0.01f) return 0;
	f = (RAS_W / 2.0f) / tanf(0.95f / 2.0f);
	o[0] = RAS_W / 2.0f + p[0] * f / p[2];
	o[1] = RAS_H / 2.0f - p[1] * f / p[2];
	o[2] = p[2];
	return 1;
}

/* Frame on the vertices actually decoded, not the stated bounding sphere:
 * the sphere has to contain the origin too, so framing on it leaves the model
 * small in the middle of the picture. */
static void ras_frame_on(const struct mesh *m, struct ras_cam *cam, float zoom, float *floor)
{
	float lo[3], hi[3], radius = 1e-3f;
	int i, any = 0, a;

	for (a = 0; a < 3; a++) { lo[a] = 1e30f; hi[a] = -1e30f; }
	for (i = 0; i < m->top; i++) {
		if (!m->vset[i]) continue;
		any = 1;
		if (m->vx[i] < lo[0]) lo[0] = m->vx[i];
		if (m->vx[i] > hi[0]) hi[0] = m->vx[i];
		if (m->vy[i] < lo[1]) lo[1] = m->vy[i];
		if (m->vy[i] > hi[1]) hi[1] = m->vy[i];
		if (m->vz[i] < lo[2]) lo[2] = m->vz[i];
		if (m->vz[i] > hi[2]) hi[2] = m->vz[i];
	}
	if (!any) { lo[0] = lo[1] = lo[2] = -1; hi[0] = hi[1] = hi[2] = 1; }
	for (a = 0; a < 3; a++) {
		cam->centre[a] = (lo[a] + hi[a]) / 2;
		if ((hi[a] - lo[a]) / 2 > radius) radius = (hi[a] - lo[a]) / 2;
	}
	cam->dist = radius * zoom;
	*floor = lo[1];
}

/* Where an object stands in the world: a position, a heading about the
 * vertical, and a scale. A scenario file gives all three per object, so one
 * model resource is drawn many times in one scene. */
struct ras_place {
	float x, y, z;			/* world position; z is height */
	float heading;			/* radians about the vertical */
	float scale;
};

static const struct ras_place RAS_HERE = { 0, 0, 0, 0, 1.0f };

/* Model space has Y up; the world puts its ground plane in x/y and height in
 * z, which is how the scenario files are written. This is the one place the
 * two conventions meet. */
static void ras_to_world(const struct ras_place *p, float mx, float my, float mz,
			 float *o)
{
	float c = cosf(p->heading), s = sinf(p->heading);

	o[0] = p->x + p->scale * (mx * c - mz * s);
	o[1] = p->z + p->scale * my;
	o[2] = p->y + p->scale * (mx * s + mz * c);
}

/* One object into an already-prepared frame. Split out of ras_draw so a scene
 * can put hundreds of them in without a merged mesh the size of a map. */
static int ras_draw_at(struct raster *f, const struct mesh *m, const struct ras_cam *cam,
		       const struct ras_place *at, float floor, int shadow)
{
	int i, k, drawn = 0;

	for (k = shadow ? 0 : 1; k < 2; k++) {
		for (i = 0; i < m->npoly; i++) {
			const struct mesh_poly *p = &m->poly[i];
			float scr[MESH_PIDX][3], cpt[MESH_PIDX][3];
			uint8_t colour[3];
			int j, ok = 1, t;

			for (j = 0; j < p->n; j++) {
				int v = p->v[j];
				float w[3];
				if (v >= MESH_VERTS || !m->vset[v]) { ok = 0; break; }
				ras_to_world(at, m->vx[v], m->vy[v], m->vz[v], w);
				ras_view(cam, w[0], k == 0 ? floor : w[1], w[2], cpt[j]);
				if (!ras_project(cpt[j], scr[j])) { ok = 0; break; }
			}
			if (!ok || p->n < 3) continue;

			if (k == 0) {
				memcpy(colour, RAS_SHADOW, 3);
			} else {
				float e1[3], e2[3], nrm[3], len, facing;
				for (j = 0; j < 3; j++) {
					e1[j] = cpt[1][j] - cpt[0][j];
					e2[j] = cpt[2][j] - cpt[0][j];
				}
				nrm[0] = e1[1] * e2[2] - e1[2] * e2[1];
				nrm[1] = e1[2] * e2[0] - e1[0] * e2[2];
				nrm[2] = e1[0] * e2[1] - e1[1] * e2[0];
				len = sqrtf(nrm[0] * nrm[0] + nrm[1] * nrm[1] + nrm[2] * nrm[2]);
				if (len < 1e-9f) continue;
				for (j = 0; j < 3; j++) nrm[j] /= len;
				facing = nrm[0] * cpt[0][0] + nrm[1] * cpt[0][1] + nrm[2] * cpt[0][2];
				if (facing > 0)
					for (j = 0; j < 3; j++) nrm[j] = -nrm[j];
				{
					int mi = p->mat < MESH_MATS ? p->mat : 0;
					float r = m->mset[mi] ? m->mr[mi] : 0.7f;
					float g = m->mset[mi] ? m->mg[mi] : 0.7f;
					float b = m->mset[mi] ? m->mb[mi] : 0.7f;
					ras_shade(colour, r, g, b, nrm, m->mset[mi] ? m->mkind[mi] : 1);
				}
				drawn++;
			}
			for (t = 1; t < p->n - 1; t++)
				ras_triangle(f, scr[0], scr[t], scr[t + 1], colour);
		}
	}
	return drawn;
}

static int ras_draw(struct raster *f, const struct mesh *m, const struct ras_cam *cam,
		    float floor, int shadow)
{
	ras_background(f, (int)(RAS_H * 0.52f));
	return ras_draw_at(f, m, cam, &RAS_HERE, floor, shadow);
}

#endif /* BATTLEPOD_RASTER_H */
