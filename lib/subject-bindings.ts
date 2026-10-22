export const SUBJECT_COLORS = [
  {name: 'red', hex: '#DC463C'}, {name: 'blue', hex: '#2D7DE1'},
  {name: 'green', hex: '#32B45A'}, {name: 'yellow', hex: '#EBCD23'},
  {name: 'magenta', hex: '#CD37B4'}, {name: 'cyan', hex: '#1EC8CD'},
  {name: 'orange', hex: '#F08223'}, {name: 'purple', hex: '#874BD2'},
] as const;
export type GuideRepresentation = 'original' | '2d' | '3d';
export type SubjectAnchor = {x: number; y: number; time_seconds: number; frame_width: number; frame_height: number};
export type SubjectBinding = {id: string; label: string; color: string; picture_slots: number[]; anchors: SubjectAnchor[]};

export function readSubjectBindings(value: unknown): SubjectBinding[] {
  if (!Array.isArray(value)) return [];
  const colors = new Set<string>(), ids = new Set<string>();
  return value.filter((raw): raw is SubjectBinding => {
    if (!raw || typeof raw !== 'object') return false;
    const s = raw as SubjectBinding;
    if (typeof s.id !== 'string' || ids.has(s.id) || typeof s.label !== 'string'
      || !SUBJECT_COLORS.some(c => c.name === s.color) || colors.has(s.color)
      || !Array.isArray(s.picture_slots) || !s.picture_slots.every(n => Number.isInteger(n) && n > 0 && n <= 11)
      || !Array.isArray(s.anchors) || !s.anchors.every(a => a && Number.isFinite(a.x) && a.x >= 0 && a.x <= 1
        && Number.isFinite(a.y) && a.y >= 0 && a.y <= 1 && Number.isFinite(a.time_seconds) && a.time_seconds >= 0
        && Number.isInteger(a.frame_width) && a.frame_width > 0 && Number.isInteger(a.frame_height) && a.frame_height > 0)) return false;
    colors.add(s.color); ids.add(s.id); return true;
  }).slice(0, SUBJECT_COLORS.length).map(s => ({...s, picture_slots: [...new Set(s.picture_slots)]}));
}

export function bindingPrompt(subjects: SubjectBinding[], representation: GuideRepresentation): string {
  if (representation === 'original') return subjects.map((s, i) => `<Subject ${i + 1}> uses the identity and appearance from ${s.picture_slots.map(n => `@Picture${n}`).join(', ')} and follows its selected performer in @Video1. Keep this assignment through position changes, occlusion and cuts.`).join(' ');
  return subjects.map((s, i) => `<Subject ${i + 1}> uses the identity and appearance from ${s.picture_slots.map(n => `@Picture${n}`).join(', ')} and follows the subject marked in ${s.color} in @Video1. Keep this assignment through position changes, occlusion and camera cuts.`).join(' ')
    + ' Guide colors identify subjects only; do not transfer marker colors or materials onto skin, fur, clothing, eyes or objects. Transfer the assigned movement, mouth articulation, blinking and gaze.';
}

// Coordinates refer to decoded pixels, excluding object-fit letterboxing.
export function videoPoint(x: number, y: number, width: number, height: number, frameWidth: number, frameHeight: number): {x: number; y: number} | null {
  if (![width, height, frameWidth, frameHeight].every(n => Number.isFinite(n) && n > 0)) return null;
  const scale = Math.min(width / frameWidth, height / frameHeight);
  const imageWidth = frameWidth * scale, imageHeight = frameHeight * scale;
  const px = (x - (width - imageWidth) / 2) / imageWidth, py = (y - (height - imageHeight) / 2) / imageHeight;
  return px >= 0 && px <= 1 && py >= 0 && py <= 1 ? {x: px, y: py} : null;
}
