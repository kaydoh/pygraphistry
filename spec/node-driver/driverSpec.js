var Rx           = require('rx');
var _            = require('underscore');
var fs           = require('fs');
var path         = require('path');
var driver       = require('../../js/node-driver.js');
var StreamGL     = require('StreamGL');
var compress     = require('node-pigz');
var renderer     = StreamGL.renderer;
var renderConfig = require('../../js/renderer.config.graph.js');

describe("Smoke test for server loop", function() {
    var activeBuffers = renderer.getServerBufferNames(renderConfig),
        activePrograms = renderConfig.scene.render;
    var anim = driver.create();

    it("Initialize animation loop", function (done) {
        var fail = this.fail;

        var tick = anim.ticks.take(1);
        tick.subscribe(function (e) {
            expect(e).not.toBeNull();
            expect(e).toBeDefined();
            done();
        }, fail);
    });

    var graph = new Rx.ReplaySubject(1);
    var ticksMulti = anim.ticks.publish();
    ticksMulti.connect();
    ticksMulti.take(1).subscribe(graph);

    it("Fetch VBO", function (done) {
        var fail = this.fail;

        graph.flatMap(function (graph) {
            return driver.fetchData(graph, compress, activeBuffers, undefined, activePrograms); 
        }).take(1).subscribe(function (vbo) {
            expect(vbo).not.toBeNull();
            expect(vbo).toBeDefined();
            done();
        }, fail);
    });
});


