/* A whole map, from the release's own scenario files.
 *
 * `Console Files/Game Files/Scenarios` holds eleven of them and they are plain
 * text. Their grammar came out of the operator console, which parses them with
 * `scanf` and logs what each line becomes - see `tools/opscon.py --formats`:
 *
 *   GROUND_CLASS    %d %d %f %f %f %f %f %d %d
 *   TERRAIN_CLASS   %d %d %f %f %f %f %f %d
 *
 * and the columns read, against the console's own `thing, class, shape, x, y,
 * z` log line, as a class, a **model resource id**, a position, a heading in
 * degrees and a scale. The id column is what makes this worth having: it names
 * a type 1 resource in the archive, which this project already decodes and
 * draws, so a scenario is a list of models to place and the whole map can be
 * drawn without a game running.
 *
 * The file also carries a block of five-column drop locations before the map,
 * terminated by `-1 -1 -1 -1 -1`, then three lines of names. Those are read
 * past rather than interpreted.
 */
#ifndef BATTLEPOD_SCENE_H
#define BATTLEPOD_SCENE_H

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "mesh.h"
#include "raster.h"

#define SCENE_MAX   2048		/* BadLands-16, the largest, places 882 */
#define SCENE_KINDS 64			/* distinct models one map draws */

struct scene_obj {
	int model;
	struct ras_place at;
};

#define SCENE_DROPS 64

/* Where a pilot starts: a facing in degrees, a position in the map's own
 * coordinates, and a height. The five-column block at the head of every
 * scenario, terminated by `-1 -1 -1 -1 -1`, which the console reads with the
 * `%f %f %f %f %d` grammar tools/opscon.py recovered. */
struct scene_drop {
	float facing, x, y, height;
};

struct scene {
	struct scene_obj obj[SCENE_MAX];
	int n;
	struct scene_drop drop[SCENE_DROPS];
	int ndrop;
	int kind[SCENE_KINDS];		/* the distinct model ids used */
	int nkind;
};

static void scene_note(struct scene *s, int model)
{
	int i;

	for (i = 0; i < s->nkind; i++)
		if (s->kind[i] == model) return;
	if (s->nkind < SCENE_KINDS) s->kind[s->nkind++] = model;
}

/* Read one scenario. Lines are counted by how many numbers they hold, which is
 * how the console tells its record types apart too - eight fields or nine,
 * with the model id in the second column either way. */
static int scene_load(struct scene *s, const char *path)
{
	char line[512];
	FILE *f = fopen(path, "rb");
	int c, n = 0;

	if (!f) return 0;
	memset(s, 0, sizeof(*s));

	/* The files are Macintosh text: CR line endings. */
	while (1) {
		double v[24];
		int nv = 0;
		char *p;

		n = 0;
		while ((c = fgetc(f)) != EOF && c != '\r' && c != '\n')
			if (n < (int)sizeof line - 1) line[n++] = (char)c;
		line[n] = 0;
		if (c == EOF && n == 0) break;

		p = line;
		while (*p && nv < 24) {
			char *e;
			double d = strtod(p, &e);
			if (e == p) break;
			v[nv++] = d;
			p = e;
			while (*p == ' ' || *p == '\t') p++;
		}
		if (nv == 5 && v[0] >= 0 && s->ndrop < SCENE_DROPS) {
			struct scene_drop *p = &s->drop[s->ndrop++];
			p->facing = (float)v[0];
			p->x = (float)v[1];
			p->y = (float)v[2];
			p->height = (float)v[3];
		}
		if ((nv == 8 || nv == 9) && s->n < SCENE_MAX) {
			struct scene_obj *o = &s->obj[s->n++];
			/* Which column names the drawable model differs by record
			 * length, and the data says which. On a nine-field record
			 * column 1 holds shapes of 0 to 7 polygons with radii in
			 * the hundreds - a collision hull - while column 8 holds
			 * real geometry: 132 polygons for the terrain mesa, 151
			 * for a building. An eight-field record has no column 8
			 * and its column 1 is the drawable one. This matches the
			 * console's own "thing, class, shape" log line having
			 * three ids to hand out. */
			o->model = (int)v[nv == 9 ? 8 : 1];
			o->at.x = (float)v[2];
			o->at.y = (float)v[3];
			o->at.z = (float)v[4];
			o->at.heading = (float)(v[5] * 3.14159265358979 / 180.0);
			o->at.scale = (float)(v[6] != 0.0 ? v[6] : 1.0);
			scene_note(s, o->model);
		}
	}
	fclose(f);
	return s->n;
}

/* Frame the camera on the whole map, looking down at it from one corner. */
static void scene_frame(const struct scene *s, struct ras_cam *cam, float *floor,
			float pad)
{
	float lo[3] = { 1e30f, 1e30f, 1e30f }, hi[3] = { -1e30f, -1e30f, -1e30f };
	int i;

	for (i = 0; i < s->n; i++) {
		const struct ras_place *p = &s->obj[i].at;
		float v[3];
		v[0] = p->x; v[1] = p->z; v[2] = p->y;
		if (v[0] < lo[0]) lo[0] = v[0];
		if (v[0] > hi[0]) hi[0] = v[0];
		if (v[1] < lo[1]) lo[1] = v[1];
		if (v[1] > hi[1]) hi[1] = v[1];
		if (v[2] < lo[2]) lo[2] = v[2];
		if (v[2] > hi[2]) hi[2] = v[2];
	}
	if (s->n == 0) { lo[0] = lo[1] = lo[2] = -1; hi[0] = hi[1] = hi[2] = 1; }
	/* Positions alone are not the extent: an object standing at the edge of
	 * the map is as wide as its own model, scaled. Without this a one-object
	 * scene frames on a single point and puts the camera inside it. */
	if (pad > 0) {
		lo[0] -= pad; lo[1] -= pad; lo[2] -= pad;
		hi[0] += pad; hi[1] += pad; hi[2] += pad;
	}
	for (i = 0; i < 3; i++) cam->centre[i] = (lo[i] + hi[i]) / 2;
	cam->dist = (hi[0] - lo[0] > hi[2] - lo[2] ? hi[0] - lo[0] : hi[2] - lo[2]);
	if (cam->dist < 1.0f) cam->dist = 1.0f;
	*floor = lo[1];
}

/* Stand at a drop point and look out across the map, which is the view the
 * cockpit actually showed.
 *
 * The camera model orbits a centre, so standing somewhere means putting the
 * centre one look-ahead in front and turning to match. A heading of h about
 * the vertical needs turn = -h: that is what makes the world direction
 * (sin h, 0, cos h) come out as straight ahead in view space.
 */
static void scene_stand(const struct scene *s, int which, struct ras_cam *cam,
			float *floor)
{
	const struct scene_drop *d;
	float h, ahead = 100.0f;

	if (s->ndrop < 1) { scene_frame(s, cam, floor, 0.0f); return; }
	if (which < 0) which = 0;
	if (which >= s->ndrop) which = s->ndrop - 1;
	d = &s->drop[which];

	h = (float)(d->facing * 3.14159265358979 / 180.0);
	cam->turn = -h;
	cam->pitch = 0.0f;
	cam->dist = ahead;
	cam->centre[0] = d->x + sinf(h) * ahead;
	cam->centre[1] = d->height;
	cam->centre[2] = d->y + cosf(h) * ahead;
	*floor = 0.0f;
}

#endif /* BATTLEPOD_SCENE_H */
