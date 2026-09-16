'use strict';

const path = require('path');

function isInside(parent, target) {
  const root = path.resolve(parent);
  const resolved = path.resolve(target);
  return resolved === root || resolved.startsWith(root + path.sep);
}

function templatesRoot(repoRoot) {
  return path.resolve(repoRoot, 'assets', 'templates');
}

function isFrozenTemplatePath(filePath, repoRoot) {
  return isInside(templatesRoot(repoRoot), filePath);
}

function assertNotTemplateWrite(filePath, repoRoot) {
  if (isFrozenTemplatePath(filePath, repoRoot)) {
    const err = new Error('TemplateProtectionError: refuse write to assets/templates');
    err.code = 'TEMPLATE_PROTECTED';
    throw err;
  }
}

function assertProjectDoc(filePath, projectRoot) {
  if (!isInside(projectRoot, filePath)) {
    const err = new Error('refuse path outside project folder: ' + filePath);
    err.code = 'OUTSIDE_PROJECT';
    throw err;
  }
}

module.exports = {
  isInside,
  templatesRoot,
  isFrozenTemplatePath,
  assertNotTemplateWrite,
  assertProjectDoc,
};
