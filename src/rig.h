/* A whole mech: parts hung on a skeleton's nodes at their rest pose.
 *
 * `tools/render.py`'s Assembly, ported. Nothing is placed by hand. A skeleton
 * is a chain of `$040` node compositions, so running the chain gives the pose;
 * a part is authored in the space of the node it hangs on and reaches from
 * that node down to the next one, so the part that belongs on a node is the
 * one whose own bounding box contains the offset of that node's child, and
 * where several do, the smallest.
 *
 * Left and right are separate resources holding mirrored geometry, and which
 * way round they go is settled by **making the part touch what it hangs
 * from**: of the two orientations, exactly one lands the thigh's inner edge on
 * the pelvis's outer edge, and it lands there to the hundredth. See
 * RENDERING.md, which also records why a rule about which way a part leans is
 * not enough.
 *
 * Two nodes are placed otherwise and say so. The torso hangs on node 2 and
 * comes from the part block ten ids above the skeleton. A foot hangs on a node
 * with nothing below it, so there is no offset to match: it is whatever is
 * left unused in the seven-id block the rest of the leg came from.
 */
#ifndef BATTLEPOD_RIG_H
#define BATTLEPOD_RIG_H

#include "mesh.h"

#define RIG_LO      460			/* the part block, inclusive */
#define RIG_HI      520
#define RIG_PARTS   (RIG_HI - RIG_LO + 1)

struct rig_part {
	uint8_t have;
	int nvert, npoly;
	/* Two extents, and the difference matters. `box` is what the model
	 * states for itself and is what decides which node a part belongs on;
	 * `lo`/`hi` are where its vertices actually are and is what decides
	 * whether two placed parts touch. Models do poke outside their stated
	 * box - RENDERING.md measures by how much - so the two are not the same
	 * and swapping them puts the legs somewhere else entirely. */
	float box[6];
	float lo[3], hi[3];
	uint32_t self, mirror;		/* vertex hashes, as authored and reflected */
};

struct rig_place {
	int node;
	uint32_t id;
	float at[3];
};

/* An order-dependent hash over the vertex slots, so a part and its reflection
 * can be recognised without keeping every mesh in memory at once. */
static uint32_t rig_hash(const struct mesh *m, int flip)
{
	uint32_t h = 2166136261u;
	int i, k;

	for (i = 0; i < m->top; i++) {
		float v[3];
		if (!m->vset[i]) continue;
		v[0] = flip ? -m->vx[i] : m->vx[i];
		v[1] = m->vy[i];
		v[2] = m->vz[i];
		for (k = 0; k < 3; k++) {
			uint32_t bits;
			float r = v[k] == 0.0f ? 0.0f : v[k];	/* -0.0 hashes as 0.0 */
			memcpy(&bits, &r, 4);
			h = (h ^ bits) * 16777619u;
		}
		h = (h ^ (uint32_t)i) * 16777619u;
	}
	return h;
}

static float rig_volume(const struct rig_part *p)
{
	float v = 1.0f;
	int a;

	for (a = 0; a < 3; a++) {
		float d = p->box[2 * a + 1] - p->box[2 * a];
		v *= d > 1e-6f ? d : 1e-6f;
	}
	return v;
}

static int rig_inside(const struct rig_part *p, const float *d)
{
	int a;

	for (a = 0; a < 3; a++)
		if (d[a] < p->box[2 * a] - 1e-3f || d[a] > p->box[2 * a + 1] + 1e-3f) return 0;
	return 1;
}

/* How well two placed parts meet: the gap between them and how much they run
 * through each other. Both near zero means they touch. */
static void rig_joins(const float *alo, const float *ahi,
		      const float *blo, const float *bhi, float *gap, float *overlap)
{
	int a;

	*gap = 0.0f;
	*overlap = 1.0f;
	for (a = 0; a < 3; a++) {
		float g1 = alo[a] - bhi[a], g2 = blo[a] - ahi[a];
		float o = (ahi[a] < bhi[a] ? ahi[a] : bhi[a]) - (alo[a] > blo[a] ? alo[a] : blo[a]);
		if (g1 > *gap) *gap = g1;
		if (g2 > *gap) *gap = g2;
		*overlap *= o > 0 ? o : 0;
	}
}

/* Copy one decoded part into the assembly, moved to where it hangs. */
static void rig_add(struct mesh *out, const struct mesh *part, const float *at)
{
	int vbase = out->top, mbase = out->nmat_top, i;

	for (i = 0; i < part->top; i++) {
		int d = vbase + i;
		if (!part->vset[i] || d >= MESH_VERTS) continue;
		out->vx[d] = part->vx[i] + at[0];
		out->vy[d] = part->vy[i] + at[1];
		out->vz[d] = part->vz[i] + at[2];
		if (!out->vset[d]) out->nvert++;
		out->vset[d] = 1;
		if (d + 1 > out->top) out->top = d + 1;
	}
	for (i = 0; i < MESH_MATS; i++) {
		int d = mbase + i;
		if (!part->mset[i] || d >= MESH_MATS) continue;
		out->mr[d] = part->mr[i];
		out->mg[d] = part->mg[i];
		out->mb[d] = part->mb[i];
		out->mkind[d] = part->mkind[i];
		if (!out->mset[d]) out->nmat++;
		out->mset[d] = 1;
		if (d + 1 > out->nmat_top) out->nmat_top = d + 1;
	}
	for (i = 0; i < part->npoly; i++) {
		const struct mesh_poly *p = &part->poly[i];
		struct mesh_poly *q;
		int j, ok = 1;

		if (out->npoly >= MESH_POLYS) break;
		q = &out->poly[out->npoly];
		q->n = p->n;
		for (j = 0; j < p->n; j++) {
			int v = vbase + p->v[j];
			if (v >= MESH_VERTS || !out->vset[v]) { ok = 0; break; }
			q->v[j] = (uint16_t)v;
		}
		if (!ok) continue;
		q->mat = (uint16_t)(mbase + p->mat);
		out->npoly++;
	}
	if (out->top < vbase) out->top = vbase;
	/* Leave a gap so the next part's slots cannot collide with this one's. */
	if (out->top < vbase + part->top) out->top = vbase + part->top;
	if (out->nmat_top < mbase + MESH_MATS && mbase + part->nmat_top > out->nmat_top)
		out->nmat_top = mbase + part->nmat_top;
}

#endif /* BATTLEPOD_RIG_H */
