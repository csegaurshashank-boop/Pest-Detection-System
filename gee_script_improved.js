
var seasonStart = '2025-06-01';
var seasonEnd = '2025-10-01';
var baselineYears = [2019,2020,2021,2022,2023];
var cloudThresh = 40;
var ndviAnomThreshold = -0.12;
var minFrac = 0.15;
var consecutiveNeeded = 3;
var recentWindow = 5;

var fields = ee.FeatureCollection([ee.Feature(/* REDACTED_GEOMETRY */)]);

function maskS2(img){
  var scl = img.select('SCL');
  var good = scl.neq(3).and(scl.neq(8)).and(scl.neq(9)).and(scl.neq(10));
  return img.updateMask(good);
}
function addNDVI(img){ return img.addBands(img.normalizedDifference(['B8','B4']).rename('NDVI')); }

var baselineImgs = ee.ImageCollection(baselineYears.map(function(y){
  var s = ee.Date.fromYMD(y,6,1);
  var e = ee.Date.fromYMD(y,10,1);
  return ee.ImageCollection('COPERNICUS/S2_SR').filterDate(s,e).filterBounds(fields)
    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', cloudThresh)).map(maskS2).map(addNDVI).select('NDVI').median();
}));
var baseline = baselineImgs.median().rename('NDVI_baseline');

var seasonCol = ee.ImageCollection('COPERNICUS/S2_SR').filterDate(seasonStart, seasonEnd).filterBounds(fields)
  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', cloudThresh)).map(maskS2).map(addNDVI).select('NDVI').sort('system:time_start');

var analyzeField = function(field){
  var geom = field.geometry();
  var baselineMean = ee.Number(baseline.reduceRegion({reducer: ee.Reducer.mean(), geometry: geom, scale:10, maxPixels:1e9}).get('NDVI_baseline')).unmask(0);
  var imgList = seasonCol.toList(seasonCol.size());
  var nImgs = imgList.size();
  var seq = ee.List.sequence(0, nImgs.subtract(1));
  var statsList = seq.map(function(i){
    var img = ee.Image(imgList.get(i));
    var date = ee.Date(img.get('system:time_start')).format('YYYY-MM-dd');
    var meanNdvi = ee.Number(img.reduceRegion({reducer: ee.Reducer.mean(), geometry: geom, scale:10, maxPixels:1e9}).get('NDVI')).unmask(0);
    var anom = meanNdvi.subtract(baselineMean);
    var isLow = anom.lte(ndviAnomThreshold);
    return ee.Dictionary({'date':date,'anom':anom,'isLow':isLow});
  });

  var lastN = ee.List(statsList).slice(ee.List(statsList).length().subtract(recentWindow).max(0));
  var isLowList = lastN.map(function(d){ return ee.Number(ee.Dictionary(d).get('isLow')).toInt(); });

  var hasConsec = (function(){
    var L = ee.List(isLowList);
    var len = L.length();
    var indices = ee.List.sequence(0, len.subtract(1));
    var found = indices.map(function(start){
      start = ee.Number(start).toInt();
      var slice = L.slice(start, start.add(consecutiveNeeded));
      var cond = ee.Algorithms.If(ee.List(slice).length().lt(consecutiveNeeded), 0, ee.List(slice).reduce(ee.Reducer.product()));
      return ee.Number(cond);
    });
    return ee.List(found).contains(1);
  })();
  var recentImg = ee.Image(imgList.get(nImgs.subtract(1))).select('NDVI');
  var recentAnomImg = recentImg.subtract(baseline);
  var belowMask = recentAnomImg.lt(ndviAnomThreshold).selfMask();
  var pixBelow = ee.Number(belowMask.reduceRegion({reducer: ee.Reducer.count(), geometry: geom, scale:10, maxPixels:1e9}).values().get(0)).max(0);
  var pixTot = ee.Number(recentImg.reduceRegion({reducer: ee.Reducer.count(), geometry: geom, scale:10, maxPixels:1e9}).values().get(0)).max(1);
  var frac = pixBelow.divide(pixTot);

  var pest = hasConsec.and(frac.gte(minFrac));

  return field.set({'n_images': nImgs, 'frac_below': frac, 'pest_detected': pest});
};

var results = fields.map(analyzeField);
print('Results sample:', results);
Map.addLayer(results.filter(ee.Filter.eq('pest_detected', 1)), {color:'red'}, 'Pest Detected');
